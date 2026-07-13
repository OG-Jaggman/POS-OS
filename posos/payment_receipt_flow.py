from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from .giftcards import build_payment_receipt, complete_gift_card_sale, lookup_card
from .printer import PrinterError, open_cash_drawer, print_receipt


def _print_copy(db, sale_id, employee, created, lines, total, payment, copy_name, cash=0, change=0, last4="", remaining=0):
    printer_row = db.default_printer()
    if not printer_row:
        return "No default receipt printer is configured."
    printer = dict(printer_row)
    try:
        receipt = build_payment_receipt(
            db.get_setting("store_name", "POS OS"), sale_id, employee, created,
            lines, total, payment, printer["paper_width_mm"], copy_name,
            cash, change, last4, remaining,
        )
        print_receipt(printer, receipt)
        return ""
    except PrinterError as exc:
        return f"{copy_name.title()} did not print: {exc}"


def patch_completed_receipt_prompt() -> None:
    from .app import DB, POSOS, money, parse_money

    if getattr(POSOS, "_posos_completed_receipt_prompt", False):
        return

    def payment_screen(self):
        if not self.cart:
            return
        lines = list(self.cart.values())
        total = sum(line["qty"] * line["price_cents"] for line in lines)

        win = tk.Toplevel(self)
        win.title("Payment")
        win.transient(self)
        win.grab_set()
        win.attributes("-topmost", True)
        win.geometry("760x570")
        outer = tk.Frame(win, bg="#f4f3ef", padx=22, pady=18)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text=f"PAY {money(total)}", bg="#f4f3ef", fg="#242424", font=("DejaVu Sans", 26, "bold")).pack(pady=(0, 12))

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
        ttk.Button(
            cash_tab,
            text="Touch keypad",
            command=lambda: cash_var.set(self.ask_number("Cash payment", f"Total: {money(total)}\nCash received", cash_var.get(), decimal=True) or cash_var.get()),
        ).pack(fill="x", pady=8, ipady=8)
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
        ttk.Button(
            card_tab,
            text="Touch keyboard",
            command=lambda: card_var.set(self.ask_text("Gift card", "Swipe or enter gift card number", card_var.get()) or card_var.get()),
        ).pack(fill="x", pady=8, ipady=8)
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
                    after = int(card["balance_cents"]) - total
                    balance_var.set(f"Balance: {money(card['balance_cents'])}    After sale: {money(after)}")
            except ValueError:
                pass
        card_var.trace_add("write", check_balance)

        def finish_receipts(sale_id, created, payment, summary, cash=0, change=0, last4="", remaining=0, open_drawer=False):
            warnings = []
            cashier_error = _print_copy(DB, sale_id, self.current_user["name"], created, lines, total, payment, "CASHIER COPY", cash, change, last4, remaining)
            if cashier_error:
                warnings.append(cashier_error)
            if open_drawer:
                printer = DB.default_printer()
                if printer and printer["drawer_enabled"]:
                    try:
                        open_cash_drawer(dict(printer))
                    except PrinterError as exc:
                        warnings.append(f"Cash drawer did not open: {exc}")

            win.destroy()
            self.update_idletasks()
            customer_copy = messagebox.askyesno(
                "Transaction complete",
                f"{summary}\n\nPrint a customer receipt?",
                parent=self,
            )
            if customer_copy:
                customer_error = _print_copy(DB, sale_id, self.current_user["name"], created, lines, total, payment, "CUSTOMER COPY", cash, change, last4, remaining)
                if customer_error:
                    warnings.append(customer_error)
            if warnings:
                messagebox.showwarning("Transaction complete", summary + "\n\n" + "\n".join(warnings), parent=self)
            self.register_screen()

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
            finish_receipts(sale_id, created, "cash", f"Change due: {money(change)}", cash=received, change=change, open_drawer=True)

        def finish_card():
            try:
                sale_id, created, last4, remaining = complete_gift_card_sale(DB, self.current_user["id"], lines, total, card_var.get())
            except Exception as exc:
                messagebox.showerror("Gift card payment", str(exc), parent=win)
                return
            finish_receipts(sale_id, created, "gift_card", f"Gift card payment complete.\nRemaining balance: {money(remaining)}", last4=last4, remaining=remaining)

        buttons = tk.Frame(outer, bg="#f4f3ef")
        buttons.pack(fill="x")
        tk.Button(buttons, text="COMPLETE CASH", command=finish_cash, bg="#ffa000", relief="flat", font=("DejaVu Sans", 14, "bold"), pady=12).pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(buttons, text="CHARGE GIFT CARD", command=finish_card, bg="#795548", fg="white", relief="flat", font=("DejaVu Sans", 14, "bold"), pady=12).pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(buttons, text="Cancel", command=win.destroy, relief="flat", font=("DejaVu Sans", 12), pady=12).pack(side="left", padx=4)
        cash_entry.focus_set()

    POSOS.cash_payment = payment_screen
    POSOS._posos_completed_receipt_prompt = True
