from __future__ import annotations

import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .db import Database
from .printer import PrinterError, build_receipt_text, print_receipt
from .security import hash_pin, verify_pin
from .updater import UpdateError, check_latest

DATA_DIR = Path(os.environ.get("POSOS_DATA_DIR", Path.home() / ".local/share/posos"))
DB = Database(DATA_DIR / "posos.db")


def money(cents: int) -> str:
    return f"${cents / 100:.2f}"


def parse_money(text: str) -> int:
    return int(round(float(text.replace("$", "").strip()) * 100))


class TouchDialog(tk.Toplevel):
    def __init__(self, parent, title: str, prompt: str, initial: str = "", numeric=False,
                 secret=False, decimal=False):
        super().__init__(parent)
        self.result = None
        self.numeric = numeric
        self.decimal = decimal
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.attributes("-topmost", True)
        self.geometry("760x620")
        self.configure(padx=18, pady=18)

        ttk.Label(self, text=prompt, font=("DejaVu Sans", 20, "bold"), wraplength=700).pack(pady=(0, 12))
        self.value = tk.StringVar(value=initial)
        self.entry = ttk.Entry(self, textvariable=self.value, show="•" if secret else "",
                               justify="center", font=("DejaVu Sans", 25))
        self.entry.pack(fill="x", ipady=10, pady=(0, 14))
        self.entry.focus_set()

        keypad = ttk.Frame(self)
        keypad.pack(fill="both", expand=True)
        if numeric:
            keys = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"],
                    ["Clear", "0", "⌫"]]
            if decimal:
                keys[-1] = ["Clear", "0", ".", "⌫"]
            for r, row in enumerate(keys):
                for c, key in enumerate(row):
                    ttk.Button(keypad, text=key, command=lambda k=key: self.press(k)).grid(
                        row=r, column=c, sticky="nsew", padx=5, pady=5, ipady=15)
                for c in range(len(row)):
                    keypad.columnconfigure(c, weight=1)
                keypad.rowconfigure(r, weight=1)
        else:
            rows = ["1234567890", "QWERTYUIOP", "ASDFGHJKL", "ZXCVBNM"]
            for r, row in enumerate(rows):
                holder = ttk.Frame(keypad)
                holder.pack(fill="both", expand=True)
                for key in row:
                    ttk.Button(holder, text=key, command=lambda k=key: self.press(k)).pack(
                        side="left", fill="both", expand=True, padx=2, pady=3)
            bottom = ttk.Frame(keypad)
            bottom.pack(fill="both", expand=True)
            ttk.Button(bottom, text="Space", command=lambda: self.press(" ")).pack(side="left", fill="both", expand=True, padx=3)
            ttk.Button(bottom, text="⌫", command=lambda: self.press("⌫")).pack(side="left", fill="both", expand=True, padx=3)
            ttk.Button(bottom, text="Clear", command=lambda: self.press("Clear")).pack(side="left", fill="both", expand=True, padx=3)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="left", fill="x", expand=True, padx=4, ipady=12)
        ttk.Button(buttons, text="OK", command=self.ok).pack(side="left", fill="x", expand=True, padx=4, ipady=12)
        self.bind("<Return>", lambda _e: self.ok())
        self.bind("<Escape>", lambda _e: self.cancel())

    def press(self, key):
        if key == "Clear":
            self.value.set("")
        elif key == "⌫":
            self.value.set(self.value.get()[:-1])
        elif key == "." and "." in self.value.get():
            return
        else:
            self.value.set(self.value.get() + key)
        self.entry.icursor("end")

    def ok(self):
        self.result = self.value.get()
        self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()


class POSOS(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("POS OS")
        self.geometry("1024x700")
        self.minsize(800, 600)
        self.current_user = None
        self.cart = {}
        self.option_add("*Font", ("DejaVu Sans", 12))
        # Kiosk safety: closing the main window would leave the OS on an unusable desktop.
        self.protocol("WM_DELETE_WINDOW", lambda: None)
        try:
            self.attributes("-fullscreen", os.environ.get("POSOS_WINDOWED") != "1")
        except Exception:
            pass
        if DB.employee_count() == 0:
            self.first_run()
        self.login_screen()

    def clear(self):
        for widget in self.winfo_children():
            widget.destroy()

    def ask_number(self, title, prompt, initial="", secret=False, decimal=False):
        dialog = TouchDialog(self, title, prompt, initial, numeric=True, secret=secret, decimal=decimal)
        self.wait_window(dialog)
        return dialog.result

    def ask_text(self, title, prompt, initial="", secret=False):
        dialog = TouchDialog(self, title, prompt, initial, numeric=False, secret=secret)
        self.wait_window(dialog)
        return dialog.result

    def first_run(self):
        messagebox.showinfo("POS OS Setup", "Create the first manager account.")
        while True:
            name = self.ask_text("Manager setup", "Manager name")
            pin = self.ask_number("Manager setup", "Create a 4–12 digit manager PIN", secret=True)
            confirm = self.ask_number("Manager setup", "Confirm manager PIN", secret=True)
            if name and pin == confirm:
                try:
                    DB.add_employee(name.strip(), hash_pin(pin), "manager")
                    return
                except ValueError as exc:
                    messagebox.showerror("Invalid PIN", str(exc))
            else:
                messagebox.showerror("Setup incomplete", "Name is required and both PIN entries must match.")

    def login_screen(self):
        self.clear()
        frame = ttk.Frame(self, padding=30)
        frame.pack(expand=True)
        ttk.Label(frame, text="POS OS", font=("DejaVu Sans", 38, "bold")).pack(pady=(0, 18))
        ttk.Label(frame, text="Employee PIN", font=("DejaVu Sans", 18)).pack()
        value = tk.StringVar()
        entry = ttk.Entry(frame, textvariable=value, show="•", font=("DejaVu Sans", 28), justify="center")
        entry.pack(fill="x", pady=12, ipady=8)
        entry.focus_set()

        def press(key):
            if key == "Clear": value.set("")
            elif key == "⌫": value.set(value.get()[:-1])
            else: value.set(value.get() + key)

        def sign_in(*_):
            for emp in DB.employee_by_pin_candidates():
                if verify_pin(value.get(), emp["pin_hash"]):
                    self.current_user = emp
                    self.register_screen()
                    return
            value.set("")
            messagebox.showerror("Login failed", "Incorrect or disabled employee PIN.")

        keypad = ttk.Frame(frame)
        keypad.pack(fill="both", expand=True)
        for r, row in enumerate([["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["Clear", "0", "⌫"]]):
            for c, key in enumerate(row):
                ttk.Button(keypad, text=key, command=lambda k=key: press(k)).grid(
                    row=r, column=c, sticky="nsew", padx=5, pady=5, ipadx=18, ipady=12)
                keypad.columnconfigure(c, weight=1)
            keypad.rowconfigure(r, weight=1)
        ttk.Button(frame, text="SIGN IN", command=sign_in).pack(fill="x", pady=(10, 0), ipady=14)
        entry.bind("<Return>", sign_in)

    def register_screen(self):
        self.clear()
        self.cart = {}
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text=f"POS OS — {self.current_user['name']}", font=("DejaVu Sans", 18, "bold")).pack(side="left")
        ttk.Button(top, text="Log out", command=self.login_screen).pack(side="right", ipadx=8, ipady=6)
        if self.current_user["role"] == "manager":
            ttk.Button(top, text="Manager", command=self.manager_screen).pack(side="right", padx=8, ipadx=8, ipady=6)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=8)
        left, right = ttk.Frame(body), ttk.Frame(body)
        body.add(left, weight=3)
        body.add(right, weight=2)

        search = tk.StringVar()
        search_row = ttk.Frame(left)
        search_row.pack(fill="x", pady=(0, 8))
        entry = ttk.Entry(search_row, textvariable=search, font=("DejaVu Sans", 18))
        entry.pack(side="left", fill="x", expand=True, ipady=7)
        entry.focus_set()
        ttk.Button(search_row, text="⌨", command=lambda: self._set_from_dialog(search, self.ask_text("Search", "Product name or barcode", search.get()))).pack(side="left", padx=(5, 0), ipadx=10, ipady=7)

        grid = ttk.Frame(left)
        grid.pack(fill="both", expand=True)

        def refresh(*_):
            for widget in grid.winfo_children(): widget.destroy()
            query = search.get().lower().strip()
            items = [i for i in DB.items(True) if query in i["name"].lower() or query in (i["barcode"] or "").lower()]
            for idx, item in enumerate(items[:60]):
                ttk.Button(grid, text=f"{item['name']}\n{money(item['price_cents'])}",
                           command=lambda i=item: self.add_item(i)).grid(
                    row=idx // 4, column=idx % 4, sticky="nsew", padx=3, pady=3, ipady=12)
            for col in range(4): grid.columnconfigure(col, weight=1)
        search.trace_add("write", refresh)
        refresh()
        entry.bind("<Return>", lambda _e: (self.scan_or_search(search.get()), search.set("")))

        self.cart_tree = ttk.Treeview(right, columns=("qty", "price", "total"), show="tree headings", height=18)
        self.cart_tree.heading("#0", text="Item")
        self.cart_tree.heading("qty", text="Qty")
        self.cart_tree.heading("price", text="Price")
        self.cart_tree.heading("total", text="Total")
        self.cart_tree.pack(fill="both", expand=True)
        self.total_label = ttk.Label(right, text="Total: $0.00", font=("DejaVu Sans", 28, "bold"))
        self.total_label.pack(pady=10)
        controls = ttk.Frame(right)
        controls.pack(fill="x")
        ttk.Button(controls, text="− Qty", command=lambda: self.change_quantity(-1)).pack(side="left", fill="x", expand=True, ipady=8)
        ttk.Button(controls, text="+ Qty", command=lambda: self.change_quantity(1)).pack(side="left", fill="x", expand=True, ipady=8)
        ttk.Button(controls, text="Remove", command=self.remove_selected).pack(side="left", fill="x", expand=True, ipady=8)
        ttk.Button(right, text="CLEAR SALE", command=self.clear_sale).pack(fill="x", pady=(8, 4), ipady=8)
        ttk.Button(right, text="CASH PAYMENT", command=self.cash_payment).pack(fill="x", pady=4, ipady=14)

    @staticmethod
    def _set_from_dialog(variable, result):
        if result is not None: variable.set(result)

    def scan_or_search(self, text):
        item = DB.item_by_barcode(text.strip())
        if item: self.add_item(item)

    def add_item(self, item):
        key = item["id"]
        self.cart.setdefault(key, {"id": key, "name": item["name"], "price_cents": item["price_cents"], "qty": 0})
        self.cart[key]["qty"] += 1
        self.refresh_cart()

    def refresh_cart(self):
        for iid in self.cart_tree.get_children(): self.cart_tree.delete(iid)
        total = 0
        for key, line in self.cart.items():
            line_total = line["qty"] * line["price_cents"]
            total += line_total
            self.cart_tree.insert("", "end", iid=str(key), text=line["name"], values=(line["qty"], money(line["price_cents"]), money(line_total)))
        self.total_label.config(text=f"Total: {money(total)}")

    def change_quantity(self, amount):
        for iid in self.cart_tree.selection():
            key = int(iid)
            self.cart[key]["qty"] += amount
            if self.cart[key]["qty"] <= 0: self.cart.pop(key, None)
        self.refresh_cart()

    def remove_selected(self):
        for iid in self.cart_tree.selection(): self.cart.pop(int(iid), None)
        self.refresh_cart()

    def clear_sale(self):
        if self.cart and messagebox.askyesno("Clear sale", "Remove every item from this sale?"):
            self.cart.clear(); self.refresh_cart()

    def cash_payment(self):
        if not self.cart: return
        total = sum(line["qty"] * line["price_cents"] for line in self.cart.values())
        raw = self.ask_number("Cash payment", f"Total: {money(total)}\nCash received", decimal=True)
        try:
            cash = parse_money(raw or "")
        except Exception:
            messagebox.showerror("Cash payment", "Enter a valid amount."); return
        if cash < total:
            messagebox.showerror("Cash payment", "Cash received is less than the total."); return
        sale_id = DB.complete_sale(self.current_user["id"], list(self.cart.values()), cash)
        change = cash - total
        messagebox.showinfo("Sale complete", f"Change due: {money(change)}")
        default = DB.default_printer()
        if default:
            try:
                receipt = build_receipt_text(DB.get_setting("store_name", "POS OS"), sale_id, self.current_user["name"], "CASH", list(self.cart.values()), total, cash, change, default["paper_width_mm"])
                print_receipt(dict(default), receipt)
            except PrinterError as exc:
                messagebox.showwarning("Receipt printer", f"Sale completed, but the receipt did not print:\n{exc}")
        self.register_screen()

    def manager_screen(self):
        if self.current_user["role"] != "manager": return
        self.clear()
        top = ttk.Frame(self, padding=8); top.pack(fill="x")
        ttk.Label(top, text="Manager Settings", font=("DejaVu Sans", 22, "bold")).pack(side="left")
        ttk.Button(top, text="Back to register", command=self.register_screen).pack(side="right", ipady=6)
        notebook = ttk.Notebook(self); notebook.pack(fill="both", expand=True, padx=8, pady=8)
        tabs = {name: ttk.Frame(notebook, padding=8) for name in ("Items", "Employees", "Sales", "Receipt Printers", "System")}
        for name, tab in tabs.items(): notebook.add(tab, text=name)
        self.build_items_tab(tabs["Items"])
        self.build_employees_tab(tabs["Employees"])
        self.build_sales_tab(tabs["Sales"])
        self.build_printers_tab(tabs["Receipt Printers"])
        self.build_system_tab(tabs["System"])

    def build_items_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("barcode", "price", "stock", "category"), show="tree headings")
        for col, text in [("#0", "Item"), ("barcode", "Barcode"), ("price", "Price"), ("stock", "Stock"), ("category", "Category")]: tree.heading(col, text=text)
        tree.pack(fill="both", expand=True)
        def load():
            tree.delete(*tree.get_children())
            for row in DB.items(False): tree.insert("", "end", iid=str(row["id"]), text=row["name"], values=(row["barcode"], money(row["price_cents"]), row["stock_qty"], row["category"]))
        def edit(new=False):
            row = None if new or not tree.selection() else DB.item_by_id(int(tree.selection()[0]))
            name = self.ask_text("Item", "Item name", row["name"] if row else "")
            if not name: return
            barcode = self.ask_text("Item", "Barcode", row["barcode"] if row else "")
            price = self.ask_number("Item", "Price", money(row["price_cents"]) if row else "0.00", decimal=True)
            category = self.ask_text("Item", "Category", row["category"] if row else "")
            stock = self.ask_number("Item", "Inventory quantity", str(row["stock_qty"] if row else 0))
            low = self.ask_number("Item", "Low-stock level", str(row["low_stock"] if row else 0))
            try:
                DB.save_item(row["id"] if row else None, name.strip(), barcode.strip(), parse_money(price), category.strip(), int(stock), int(low), True)
                load()
            except Exception as exc: messagebox.showerror("Item", str(exc))
        bar = ttk.Frame(parent); bar.pack(fill="x", pady=(8,0))
        for text, command in [("Add item", lambda: edit(True)), ("Edit selected", edit), ("Delete selected", lambda: self._delete_selected(tree, DB.delete_item, load))]:
            ttk.Button(bar, text=text, command=command).pack(side="left", fill="x", expand=True, ipady=9)
        load()

    def build_employees_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("role", "active"), show="tree headings")
        tree.heading("#0", text="Employee"); tree.heading("role", text="Role"); tree.heading("active", text="Active")
        tree.pack(fill="both", expand=True)
        def load():
            tree.delete(*tree.get_children())
            for row in DB.employees(): tree.insert("", "end", iid=str(row["id"]), text=row["name"], values=(row["role"], "Yes" if row["active"] else "No"))
        def edit(new=False):
            row = None if new or not tree.selection() else DB.employee_by_id(int(tree.selection()[0]))
            name = self.ask_text("Employee", "Employee name", row["name"] if row else "")
            if not name: return
            role = self.ask_text("Employee", "Role: cashier or manager", row["role"] if row else "cashier")
            role = role.lower().strip()
            if role not in ("cashier", "manager"):
                messagebox.showerror("Role", "Role must be cashier or manager."); return
            pin = self.ask_number("Employee", "New PIN (leave blank to keep current)", secret=True)
            try:
                pin_hash = hash_pin(pin) if pin else None
                eid = row["id"] if row else None
                if eid: DB.update_employee(eid, name.strip(), role, True, pin_hash)
                elif pin_hash: DB.add_employee(name.strip(), pin_hash, role)
                else: raise ValueError("A PIN is required for a new employee.")
                load()
            except Exception as exc: messagebox.showerror("Employee", str(exc))
        bar = ttk.Frame(parent); bar.pack(fill="x", pady=(8,0))
        for text, command in [("Add employee", lambda: edit(True)), ("Edit selected", edit), ("Delete selected", lambda: self._delete_selected(tree, DB.delete_employee, load))]:
            ttk.Button(bar, text=text, command=command).pack(side="left", fill="x", expand=True, ipady=9)
        load()

    def build_sales_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("employee", "total", "cash", "change", "time"), show="headings")
        for col in ("employee", "total", "cash", "change", "time"): tree.heading(col, text=col.title())
        tree.pack(fill="both", expand=True)
        for row in DB.sales(): tree.insert("", "end", values=(row["employee_name"], money(row["total_cents"]), money(row["cash_cents"]), money(row["change_cents"]), row["created_at"]))

    def build_printers_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("type", "destination", "paper", "default"), show="tree headings")
        for col, text in [("#0", "Printer"), ("type", "Type"), ("destination", "Destination"), ("paper", "Paper"), ("default", "Default")]: tree.heading(col, text=text)
        tree.pack(fill="both", expand=True)
        def destination(row):
            if row["printer_type"] == "network": return f"{row['host']}:{row['port']}"
            if row["printer_type"] in ("system", "cups", "windows"): return row["queue_name"] or "Default queue"
            return row["file_path"]
        def load():
            tree.delete(*tree.get_children())
            for row in DB.printers(): tree.insert("", "end", iid=str(row["id"]), text=row["name"], values=(row["printer_type"], destination(row), f"{row['paper_width_mm']} mm", "Yes" if row["is_default"] else ""))
        def edit(new=False):
            row = None if new or not tree.selection() else DB.printer_by_id(int(tree.selection()[0]))
            win = tk.Toplevel(self); win.title("Receipt printer"); win.transient(self); win.grab_set(); win.geometry("760x650")
            outer = ttk.Frame(win, padding=16); outer.pack(fill="both", expand=True)
            defaults = {"name": row["name"] if row else "Receipt Printer", "type": row["printer_type"] if row else "network", "host": row["host"] if row else "", "port": str(row["port"] if row else 9100), "queue": row["queue_name"] if row else "", "file": row["file_path"] if row else str(DATA_DIR / "test-receipt.txt"), "paper": str(row["paper_width_mm"] if row else 80)}
            variables = {k: tk.StringVar(value=v) for k,v in defaults.items()}
            fields = [("Printer name", "name"), ("IP address / hostname", "host"), ("Port", "port"), ("System/Windows queue name", "queue"), ("Test file path", "file")]
            for idx, (label, key) in enumerate(fields):
                ttk.Label(outer, text=label).grid(row=idx, column=0, sticky="w", pady=6)
                ttk.Entry(outer, textvariable=variables[key]).grid(row=idx, column=1, sticky="ew", padx=6, pady=6, ipady=6)
                ttk.Button(outer, text="⌨", command=lambda v=variables[key], n=(key=="port"): self._edit_var(v,n)).grid(row=idx, column=2, pady=6)
            ttk.Label(outer, text="Printer type").grid(row=5, column=0, sticky="w", pady=6)
            ttk.Combobox(win, textvariable=variables["type"], state="readonly", values=("network", "system", "cups", "windows", "file")).grid(row=5, column=1, sticky="ew", padx=6, pady=6)
            ttk.Label(outer, text="Receipt paper width").grid(row=6, column=0, sticky="w", pady=6)
            ttk.Combobox(outer, textvariable=variables["paper"], state="readonly", values=("80", "58")).grid(row=6, column=1, sticky="ew", padx=6, pady=6)
            auto_cut = tk.BooleanVar(value=bool(row["auto_cut"]) if row else True); default = tk.BooleanVar(value=bool(row["is_default"]) if row else True)
            ttk.Checkbutton(outer, text="Send auto-cut command", variable=auto_cut).grid(row=7, column=0, columnspan=2, sticky="w", pady=8)
            ttk.Checkbutton(outer, text="Use as default receipt printer", variable=default).grid(row=8, column=0, columnspan=2, sticky="w", pady=8)
            ttk.Label(outer, text="Network printers normally use raw ESC/POS on TCP port 9100. System/CUPS and Windows types use an installed printer queue.", wraplength=650).grid(row=9, column=0, columnspan=3, sticky="w", pady=12)
            outer.columnconfigure(1, weight=1)
            def save():
                try:
                    DB.save_printer(row["id"] if row else None, variables["name"].get().strip(), variables["type"].get(), variables["host"].get().strip(), int(variables["port"].get() or 9100), variables["queue"].get().strip(), variables["file"].get().strip(), int(variables["paper"].get()), auto_cut.get(), default.get(), True)
                    win.destroy(); load()
                except Exception as exc: messagebox.showerror("Printer", str(exc), parent=win)
            ttk.Button(outer, text="Save printer", command=save).grid(row=10, column=0, columnspan=3, sticky="ew", ipady=12)
        def test():
            if not tree.selection(): return
            row = DB.printer_by_id(int(tree.selection()[0]))
            sample = build_receipt_text(DB.get_setting("store_name", "POS OS"), 123, self.current_user["name"], "TEST", [{"name": "Test Item", "qty": 1, "price_cents": 199}], 199, 500, 301, row["paper_width_mm"])
            try:
                print_receipt(dict(row), sample); messagebox.showinfo("Printer test", "Test receipt sent.")
            except PrinterError as exc: messagebox.showerror("Printer test failed", str(exc))
        bar = ttk.Frame(parent); bar.pack(fill="x", pady=(8, 0))
        for text, command in [("Add printer", lambda: edit(True)), ("Edit selected", edit), ("Test selected", test), ("Delete selected", lambda: self._delete_selected(tree, DB.delete_printer, load))]:
            ttk.Button(bar, text=text, command=command).pack(side="left", fill="x", expand=True, ipady=9)
        load()

    def _edit_var(self, variable, numeric=False):
        result = self.ask_number("Enter value", "Enter value", variable.get()) if numeric else self.ask_text("Enter value", "Enter value", variable.get())
        if result is not None: variable.set(result)

    def build_system_tab(self, parent):
        ttk.Label(parent, text="POS OS contains no tax calculation. Item prices are final prices.", font=("DejaVu Sans", 14, "bold")).pack(anchor="w", pady=8)
        store = ttk.Frame(parent); store.pack(fill="x", pady=8)
        ttk.Label(store, text="Store name on receipts:").pack(side="left")
        store_name = tk.StringVar(value=DB.get_setting("store_name", "POS OS"))
        ttk.Entry(store, textvariable=store_name).pack(side="left", fill="x", expand=True, padx=8, ipady=6)
        ttk.Button(store, text="⌨", command=lambda: self._edit_var(store_name)).pack(side="left")
        ttk.Button(store, text="Save", command=lambda: DB.set_setting("store_name", store_name.get().strip() or "POS OS")).pack(side="left", padx=5)
        ttk.Button(parent, text="Back up database", command=self.backup_database).pack(anchor="w", fill="x", pady=5, ipady=8)
        ttk.Button(parent, text="Check for updates", command=self.check_for_updates).pack(anchor="w", fill="x", pady=5, ipady=8)

    def backup_database(self):
        destination = DATA_DIR / "backups"
        destination.mkdir(parents=True, exist_ok=True)
        filename = destination / "posos-manual-backup.db"
        shutil.copy2(DB.path, filename)
        messagebox.showinfo("Backup", f"Backup saved to {filename}")

    def check_for_updates(self):
        repo = DB.get_setting("github_repo", "OG-Jaggman/POS-OS")
        version_file = Path(__file__).resolve().parent.parent / "VERSION"
        try:
            current = version_file.read_text(encoding="utf-8").strip()
        except OSError:
            current = "0.0.0"

        status = tk.Toplevel(self)
        status.title("POS OS Updates")
        status.transient(self)
        status.grab_set()
        status.attributes("-topmost", True)
        status.geometry("700x420")
        frame = ttk.Frame(status, padding=24)
        frame.pack(fill="both", expand=True)
        label = ttk.Label(frame, text="Checking GitHub for updates…", font=("DejaVu Sans", 18, "bold"), wraplength=640, justify="center")
        label.pack(fill="both", expand=True, pady=20)
        close = ttk.Button(frame, text="Close", command=status.destroy, state="disabled")
        close.pack(fill="x", ipady=10)

        def do_check():
            try:
                result = check_latest(repo, current)
                latest = result.get("version") or "unknown"
                if result.get("available"):
                    notes = (result.get("notes") or "No release notes were provided.").strip()
                    text = f"Update available: v{latest}\n\nInstalled version: v{current}\n\n{notes}"
                else:
                    text = f"POS OS is up to date.\n\nInstalled version: v{current}"
            except Exception as exc:
                text = f"Could not check for updates.\n\n{exc}"
            label.configure(text=text)
            close.configure(state="normal")

        self.after(150, do_check)

    def manager_exit(self):
        # Kept as a no-op for older internal calls. POS OS is a kiosk and must stay open.
        return


def main():
    POSOS().mainloop()
