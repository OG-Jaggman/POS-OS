from __future__ import annotations

import hashlib
import re
import subprocess
import tkinter as tk
from tkinter import messagebox, ttk

from .printer import PrinterError, ReceiptLayout, open_cash_drawer, print_receipt


def _ensure_schema(db) -> None:
    db.conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS gift_cards (
            id INTEGER PRIMARY KEY,
            card_hash TEXT NOT NULL UNIQUE,
            last4 TEXT NOT NULL,
            balance_cents INTEGER NOT NULL DEFAULT 0 CHECK(balance_cents >= 0),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS gift_card_transactions (
            id INTEGER PRIMARY KEY,
            gift_card_id INTEGER NOT NULL,
            employee_id INTEGER NOT NULL,
            sale_id INTEGER,
            amount_cents INTEGER NOT NULL,
            transaction_type TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(gift_card_id) REFERENCES gift_cards(id),
            FOREIGN KEY(employee_id) REFERENCES employees(id),
            FOREIGN KEY(sale_id) REFERENCES sales(id)
        );
        """
    )
    columns = {row["name"] for row in db.conn.execute("PRAGMA table_info(sales)")}
    for name, definition in {
        "payment_method": "TEXT NOT NULL DEFAULT 'cash'",
        "gift_card_last4": "TEXT NOT NULL DEFAULT ''",
    }.items():
        if name not in columns:
            db.conn.execute(f"ALTER TABLE sales ADD COLUMN {name} {definition}")
    db.conn.commit()


def normalize_card(raw: str) -> str:
    value = (raw or "").strip()
    if value.startswith("%B") and "^" in value:
        value = value[2:].split("^", 1)[0]
    elif value.startswith(";") and "=" in value:
        value = value[1:].split("=", 1)[0]
    value = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if len(value) < 4:
        raise ValueError("Gift card number must contain at least 4 characters.")
    return value


def card_hash(number: str) -> str:
    return hashlib.sha256(number.encode("utf-8")).hexdigest()


def lookup_card(db, raw: str):
    _ensure_schema(db)
    number = normalize_card(raw)
    return db.conn.execute("SELECT * FROM gift_cards WHERE card_hash=?", (card_hash(number),)).fetchone()


def issue_card(db, employee_id: int, raw: str, amount_cents: int) -> int:
    _ensure_schema(db)
    number = normalize_card(raw)
    if amount_cents < 0:
        raise ValueError("Starting balance cannot be negative.")
    now = db.now()
    cursor = db.conn.execute(
        "INSERT INTO gift_cards(card_hash,last4,balance_cents,active,created_at,updated_at) VALUES(?,?,?,?,?,?)",
        (card_hash(number), number[-4:], amount_cents, 1, now, now),
    )
    card_id = int(cursor.lastrowid)
    if amount_cents:
        db.conn.execute(
            "INSERT INTO gift_card_transactions(gift_card_id,employee_id,amount_cents,transaction_type,created_at) VALUES(?,?,?,?,?)",
            (card_id, employee_id, amount_cents, "issue", now),
        )
    db.conn.commit()
    return card_id


def load_card(db, card_id: int, employee_id: int, amount_cents: int) -> None:
    if amount_cents <= 0:
        raise ValueError("Load amount must be greater than zero.")
    now = db.now()
    db.conn.execute("UPDATE gift_cards SET balance_cents=balance_cents+?,active=1,updated_at=? WHERE id=?", (amount_cents, now, card_id))
    db.conn.execute(
        "INSERT INTO gift_card_transactions(gift_card_id,employee_id,amount_cents,transaction_type,created_at) VALUES(?,?,?,?,?)",
        (card_id, employee_id, amount_cents, "load", now),
    )
    db.conn.commit()


def complete_gift_card_sale(db, employee_id: int, lines: list[dict], total: int, raw_card: str):
    _ensure_schema(db)
    number = normalize_card(raw_card)
    now = db.now()
    try:
        db.conn.execute("BEGIN IMMEDIATE")
        card = db.conn.execute("SELECT * FROM gift_cards WHERE card_hash=?", (card_hash(number),)).fetchone()
        if not card or not card["active"]:
            raise ValueError("Gift card was not found or is inactive.")
        if int(card["balance_cents"]) < total:
            raise ValueError(f"Gift card balance is only ${card['balance_cents'] / 100:.2f}.")
        sale_cursor = db.conn.execute(
            "INSERT INTO sales(employee_id,total_cents,cash_cents,change_cents,created_at,payment_method,gift_card_last4) VALUES(?,?,?,?,?,?,?)",
            (employee_id, total, 0, 0, now, "gift_card", card["last4"]),
        )
        sale_id = int(sale_cursor.lastrowid)
        for line in lines:
            db.conn.execute(
                "INSERT INTO sale_lines(sale_id,item_id,item_name,unit_price_cents,quantity,line_total_cents) VALUES(?,?,?,?,?,?)",
                (sale_id, line["id"], line["name"], line["price_cents"], line["qty"], line["price_cents"] * line["qty"]),
            )
            if line["id"]:
                db.conn.execute("UPDATE items SET stock_qty=MAX(0,stock_qty-?) WHERE id=?", (line["qty"], line["id"]))
        db.conn.execute("UPDATE gift_cards SET balance_cents=balance_cents-?,updated_at=? WHERE id=?", (total, now, card["id"]))
        db.conn.execute(
            "INSERT INTO gift_card_transactions(gift_card_id,employee_id,sale_id,amount_cents,transaction_type,created_at) VALUES(?,?,?,?,?,?)",
            (card["id"], employee_id, sale_id, -total, "sale", now),
        )
        remaining = int(card["balance_cents"]) - total
        db.conn.commit()
        return sale_id, now, str(card["last4"]), remaining
    except Exception:
        db.conn.rollback()
        raise


def build_payment_receipt(store: str, sale_id: int, employee: str, created: str, lines: list[dict], total: int, payment: str, paper: int, copy_name: str, cash: int = 0, change: int = 0, last4: str = "", remaining: int = 0) -> str:
    layout = ReceiptLayout(paper)
    out = [layout.center(store or "POS OS"), layout.center(copy_name), layout.rule(), layout.line(f"Sale #{sale_id}", created), layout.line("Employee", employee), layout.rule()]
    for item in lines:
        qty = int(item["qty"])
        unit = int(item["price_cents"])
        out.extend([str(item["name"])[: layout.chars_per_line], layout.line(f"  {qty} x ${unit / 100:.2f}", f"${qty * unit / 100:.2f}")])
    out.extend([layout.rule(), layout.line("TOTAL", f"${total / 100:.2f}")])
    if payment == "cash":
        out.extend([layout.line("Cash", f"${cash / 100:.2f}"), layout.line("Change", f"${change / 100:.2f}")])
    else:
        out.extend([layout.line(f"Gift card ...{last4}", f"${total / 100:.2f}"), layout.line("Remaining balance", f"${remaining / 100:.2f}")])
    out.extend([layout.rule(), layout.center("Thank you!"), "", "", ""])
    return "\n".join(out)


def _print_copies(db, sale_id, employee, created, lines, total, payment, customer_copy, cash=0, change=0, last4="", remaining=0):
    printer_row = db.default_printer()
    warnings = []
    if not printer_row:
        return ["No default receipt printer is configured."]
    printer = dict(printer_row)
    copies = ["CASHIER COPY"] + (["CUSTOMER COPY"] if customer_copy else [])
    for copy_name in copies:
        try:
            receipt = build_payment_receipt(db.get_setting("store_name", "POS OS"), sale_id, employee, created, lines, total, payment, printer["paper_width_mm"], copy_name, cash, change, last4, remaining)
            print_receipt(printer, receipt)
        except PrinterError as exc:
            warnings.append(f"{copy_name.title()} did not print: {exc}")
    return warnings


def patch_payment_screen() -> None:
    from .app import DB, POSOS, money, parse_money

    if getattr(POSOS, "_posos_gift_card_payment_patch", False):
        return
    _ensure_schema(DB)

    def cash_payment(self):
        if not self.cart:
            return
        lines = list(self.cart.values())
        total = sum(line["qty"] * line["price_cents"] for line in lines)
        win = tk.Toplevel(self)
        win.title("Payment")
        win.transient(self)
        win.grab_set()
        win.attributes("-topmost", True)
        win.geometry("760x600")
        outer = tk.Frame(win, bg="#f4f3ef", padx=22, pady=18)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text=f"PAY {money(total)}", bg="#f4f3ef", fg="#242424", font=("DejaVu Sans", 26, "bold")).pack(pady=(0, 12))
        customer_copy = tk.BooleanVar(value=True)
        tk.Checkbutton(outer, text="Print customer receipt", variable=customer_copy, bg="#f4f3ef", font=("DejaVu Sans", 12)).pack()
        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True, pady=12)
        cash_tab = ttk.Frame(notebook, padding=18)
        card_tab = ttk.Frame(notebook, padding=18)
        notebook.add(cash_tab, text="Cash")
        notebook.add(card_tab, text="Gift Card / MSR")

        cash_var = tk.StringVar()
        change_var = tk.StringVar(value="Change: $0.00")
        ttk.Label(cash_tab, text="Cash received", font=("DejaVu Sans", 16, "bold")).pack(pady=(5, 8))
        cash_entry = ttk.Entry(cash_tab, textvariable=cash_var, font=("DejaVu Sans", 24), justify="center")
        cash_entry.pack(fill="x", ipady=8)
        ttk.Button(cash_tab, text="Touch keypad", command=lambda: cash_var.set(self.ask_number("Cash payment", f"Total: {money(total)}\nCash received", cash_var.get(), decimal=True) or cash_var.get())).pack(fill="x", pady=8, ipady=8)
        ttk.Label(cash_tab, textvariable=change_var, font=("DejaVu Sans", 21, "bold")).pack(pady=10)

        def update_change(*_):
            try:
                received = parse_money(cash_var.get())
                change_var.set(f"Change: {money(max(0, received - total))}")
            except Exception:
                change_var.set("Change: $0.00")
        cash_var.trace_add("write", update_change)

        card_var = tk.StringVar()
        balance_var = tk.StringVar(value="Swipe or enter a gift card")
        ttk.Label(card_tab, text="Swipe gift card now, or type the number", font=("DejaVu Sans", 15, "bold")).pack(pady=(5, 8))
        card_entry = ttk.Entry(card_tab, textvariable=card_var, font=("DejaVu Sans", 20), justify="center")
        card_entry.pack(fill="x", ipady=8)
        ttk.Button(card_tab, text="Touch keyboard", command=lambda: card_var.set(self.ask_text("Gift card", "Swipe or enter gift card number", card_var.get()) or card_var.get())).pack(fill="x", pady=8, ipady=8)
        ttk.Label(card_tab, textvariable=balance_var, font=("DejaVu Sans", 17, "bold")).pack(pady=10)

        def check_balance(*_):
            raw = card_var.get().strip()
            if len(raw) < 4:
                balance_var.set("Swipe or enter a gift card")
                return
            try:
                card = lookup_card(DB, raw)
                if not card:
                    balance_var.set("Card not found")
                elif not card["active"]:
                    balance_var.set("Card is inactive")
                else:
                    balance_var.set(f"Balance: {money(card['balance_cents'])}    After sale: {money(card['balance_cents'] - total)}")
            except ValueError:
                pass
        card_var.trace_add("write", check_balance)

        def finish_cash():
            try:
                received = parse_money(cash_var.get())
            except Exception:
                messagebox.showerror("Cash payment", "Enter a valid cash amount.", parent=win)
                return
            if received < total:
                messagebox.showerror("Cash payment", "Cash received is less than the total.", parent=win)
                return
            change = received - total
            sale_id, created = DB.complete_sale(self.current_user["id"], lines, total, received, change)
            warnings = _print_copies(DB, sale_id, self.current_user["name"], created, lines, total, "cash", customer_copy.get(), cash=received, change=change)
            printer = DB.default_printer()
            if printer and printer["drawer_enabled"]:
                try:
                    open_cash_drawer(dict(printer))
                except PrinterError as exc:
                    warnings.append(f"Cash drawer did not open: {exc}")
            win.destroy()
            messagebox.showwarning("Sale complete", f"Change due: {money(change)}\n\n" + "\n".join(warnings)) if warnings else messagebox.showinfo("Sale complete", f"Change due: {money(change)}")
            self.register_screen()

        def finish_card():
            try:
                sale_id, created, last4, remaining = complete_gift_card_sale(DB, self.current_user["id"], lines, total, card_var.get())
            except Exception as exc:
                messagebox.showerror("Gift card payment", str(exc), parent=win)
                return
            warnings = _print_copies(DB, sale_id, self.current_user["name"], created, lines, total, "gift_card", customer_copy.get(), last4=last4, remaining=remaining)
            win.destroy()
            text = f"Gift card payment complete.\nRemaining balance: {money(remaining)}"
            messagebox.showwarning("Sale complete", text + "\n\n" + "\n".join(warnings)) if warnings else messagebox.showinfo("Sale complete", text)
            self.register_screen()

        button_bar = tk.Frame(outer, bg="#f4f3ef")
        button_bar.pack(fill="x")
        tk.Button(button_bar, text="COMPLETE CASH", command=finish_cash, bg="#ffa000", relief="flat", font=("DejaVu Sans", 14, "bold"), pady=12).pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(button_bar, text="CHARGE GIFT CARD", command=finish_card, bg="#795548", fg="white", relief="flat", font=("DejaVu Sans", 14, "bold"), pady=12).pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(button_bar, text="Cancel", command=win.destroy, relief="flat", font=("DejaVu Sans", 12), pady=12).pack(side="left", padx=4)
        cash_entry.focus_set()

    POSOS.cash_payment = cash_payment
    POSOS._posos_gift_card_payment_patch = True


def build_gift_cards_tab(root, parent) -> None:
    from .app import DB, money, parse_money
    _ensure_schema(DB)
    tree = ttk.Treeview(parent, columns=("last4", "balance", "active", "updated"), show="headings")
    for col, title in (("last4", "Card"), ("balance", "Balance"), ("active", "Active"), ("updated", "Updated")):
        tree.heading(col, text=title)
    tree.pack(fill="both", expand=True)

    def refresh():
        tree.delete(*tree.get_children())
        for row in DB.conn.execute("SELECT * FROM gift_cards ORDER BY id DESC"):
            tree.insert("", "end", iid=str(row["id"]), values=(f"•••• {row['last4']}", money(row["balance_cents"]), "Yes" if row["active"] else "No", row["updated_at"]))

    def issue():
        raw = root.ask_text("Issue Gift Card", "Swipe card with MSR or enter card number")
        if not raw:
            return
        amount = root.ask_number("Issue Gift Card", "Starting balance", "0.00", decimal=True)
        try:
            issue_card(DB, root.current_user["id"], raw, parse_money(amount or "0"))
            refresh()
            messagebox.showinfo("Gift Card", "Gift card created.")
        except Exception as exc:
            messagebox.showerror("Gift Card", str(exc))

    def selected_id():
        if not tree.selection():
            messagebox.showinfo("Gift Cards", "Select a gift card first.")
            return None
        return int(tree.selection()[0])

    def load_selected():
        cid = selected_id()
        if cid is None:
            return
        amount = root.ask_number("Load Gift Card", "Amount to add", "10.00", decimal=True)
        try:
            load_card(DB, cid, root.current_user["id"], parse_money(amount or "0"))
            refresh()
        except Exception as exc:
            messagebox.showerror("Gift Card", str(exc))

    def toggle_active():
        cid = selected_id()
        if cid is None:
            return
        row = DB.conn.execute("SELECT active FROM gift_cards WHERE id=?", (cid,)).fetchone()
        DB.conn.execute("UPDATE gift_cards SET active=?,updated_at=? WHERE id=?", (0 if row["active"] else 1, DB.now(), cid))
        DB.conn.commit()
        refresh()

    bar = ttk.Frame(parent)
    bar.pack(fill="x", pady=(8, 0))
    for text, command in (("Issue / Swipe New Card", issue), ("Load Selected", load_selected), ("Activate / Deactivate", toggle_active), ("Refresh", refresh)):
        ttk.Button(bar, text=text, command=command).pack(side="left", fill="x", expand=True, padx=2, ipady=9)
    ttk.Label(parent, text="MSR readers work as keyboards: swipe the card while the card-number field is active. Card numbers are stored as hashes; only the last four characters are displayed.", wraplength=900).pack(anchor="w", pady=8)
    refresh()


def patch_gift_card_manager_tab() -> None:
    if getattr(ttk.Notebook, "_posos_gift_card_hook", False):
        return
    original_add = ttk.Notebook.add

    def add(self, child, **kwargs):
        result = original_add(self, child, **kwargs)
        if kwargs.get("text") == "Sales" and not getattr(self, "_posos_gift_cards_added", False):
            self._posos_gift_cards_added = True
            tab = ttk.Frame(self, padding=8)
            original_add(self, tab, text="Gift Cards")
            build_gift_cards_tab(self.winfo_toplevel(), tab)
        return result

    ttk.Notebook.add = add
    ttk.Notebook._posos_gift_card_hook = True
