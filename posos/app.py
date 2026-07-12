from __future__ import annotations

import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .db import Database
from .printer import PrinterError, build_receipt_text, print_receipt
from .security import hash_pin, verify_pin

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
        self.protocol("WM_DELETE_WINDOW", self.manager_exit)
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
            if cash < total: raise ValueError
        except Exception:
            messagebox.showerror("Payment", "Cash amount must be at least the total.")
            return
        change = cash - total
        lines = list(self.cart.values())
        sale_id, created_at = DB.complete_sale(self.current_user["id"], lines, total, cash, change)
        printer = DB.default_printer()
        print_error = None
        if printer:
            receipt = build_receipt_text(DB.get_setting("store_name", "POS OS"), sale_id,
                                         self.current_user["name"], created_at, lines,
                                         total, cash, change, printer["paper_width_mm"])
            try:
                print_receipt(dict(printer), receipt)
            except PrinterError as exc:
                print_error = str(exc)
        text = f"Sale #{sale_id}\nChange: {money(change)}"
        if print_error: text += f"\n\nReceipt was saved, but printing failed:\n{print_error}"
        messagebox.showinfo("Sale complete", text)
        self.cart = {}
        self.refresh_cart()

    def manager_screen(self):
        if self.current_user["role"] != "manager": return
        self.clear()
        top = ttk.Frame(self, padding=8); top.pack(fill="x")
        ttk.Label(top, text="Manager Settings", font=("DejaVu Sans", 22, "bold")).pack(side="left")
        ttk.Button(top, text="Back to register", command=self.register_screen).pack(side="right", ipadx=8, ipady=6)
        notebook = ttk.Notebook(self); notebook.pack(fill="both", expand=True, padx=10, pady=10)
        tabs = {name: ttk.Frame(notebook, padding=8) for name in ("Items", "Employees", "Sales", "Receipt Printers", "System")}
        for name, tab in tabs.items(): notebook.add(tab, text=name)
        self.build_items_tab(tabs["Items"])
        self.build_employees_tab(tabs["Employees"])
        self.build_sales_tab(tabs["Sales"])
        self.build_printers_tab(tabs["Receipt Printers"])
        self.build_system_tab(tabs["System"])

    def build_items_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("barcode", "price", "category", "stock", "active"), show="tree headings")
        tree.pack(fill="both", expand=True)
        for col, text in [("#0", "Name"), ("barcode", "Barcode"), ("price", "Price"), ("category", "Category"), ("stock", "Stock"), ("active", "Active")]: tree.heading(col, text=text)
        def load():
            tree.delete(*tree.get_children())
            for item in DB.items(): tree.insert("", "end", iid=str(item["id"]), text=item["name"], values=(item["barcode"] or "", money(item["price_cents"]), item["category"], item["stock_qty"], "Yes" if item["active"] else "No"))
        def edit(new=False):
            iid = None if new or not tree.selection() else int(tree.selection()[0])
            row = DB.item_by_id(iid) if iid else None
            name = self.ask_text("Item", "Item name", row["name"] if row else "")
            if name is None: return
            barcode = self.ask_number("Item", "Barcode (may be blank)", row["barcode"] if row and row["barcode"] else "")
            price = self.ask_number("Item", "Price", f"{row['price_cents']/100:.2f}" if row else "0.00", decimal=True)
            category = self.ask_text("Item", "Category", row["category"] if row else "General")
            stock = self.ask_number("Item", "Stock quantity", str(row["stock_qty"] if row else 0))
            low = self.ask_number("Item", "Low-stock warning", str(row["low_stock"] if row else 0))
            try:
                DB.save_item(iid, name.strip(), barcode or "", parse_money(price or "0"), (category or "General").strip(), int(stock or 0), int(low or 0), True)
                load()
            except Exception as exc: messagebox.showerror("Cannot save", str(exc))
        bar = ttk.Frame(parent); bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="Add item", command=lambda: edit(True)).pack(side="left", fill="x", expand=True, ipady=9)
        ttk.Button(bar, text="Edit selected", command=edit).pack(side="left", fill="x", expand=True, ipady=9)
        ttk.Button(bar, text="Delete selected", command=lambda: self._delete_selected(tree, DB.delete_item, load)).pack(side="left", fill="x", expand=True, ipady=9)
        load()

    def build_employees_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("role", "active"), show="tree headings")
        tree.pack(fill="both", expand=True); tree.heading("#0", text="Name"); tree.heading("role", text="Role"); tree.heading("active", text="Active")
        def load():
            tree.delete(*tree.get_children())
            for emp in DB.employees(): tree.insert("", "end", iid=str(emp["id"]), text=emp["name"], values=(emp["role"], "Yes" if emp["active"] else "No"))
        def edit(new=False):
            eid = None if new or not tree.selection() else int(tree.selection()[0])
            row = DB.employee_by_id(eid) if eid else None
            name = self.ask_text("Employee", "Employee name", row["name"] if row else "")
            if name is None: return
            pin = self.ask_number("Employee", "New PIN (leave blank to keep current PIN)", secret=True)
            role = self.ask_text("Employee", "Role: cashier or manager", row["role"] if row else "cashier")
            role = (role or "cashier").lower().strip()
            if role not in ("cashier", "manager"):
                messagebox.showerror("Role", "Role must be cashier or manager."); return
            try:
                pin_hash = hash_pin(pin) if pin else None
                if not eid and not pin_hash: raise ValueError("A PIN is required for a new employee")
                if eid: DB.update_employee(eid, name.strip(), role, True, pin_hash)
                else: DB.add_employee(name.strip(), pin_hash, role)
                load()
            except Exception as exc: messagebox.showerror("Cannot save", str(exc))
        bar = ttk.Frame(parent); bar.pack(fill="x", pady=(8, 0))
        ttk.Button(bar, text="Add employee", command=lambda: edit(True)).pack(side="left", fill="x", expand=True, ipady=9)
        ttk.Button(bar, text="Edit selected", command=edit).pack(side="left", fill="x", expand=True, ipady=9)
        ttk.Button(bar, text="Delete selected", command=lambda: self._delete_selected(tree, DB.delete_employee, load)).pack(side="left", fill="x", expand=True, ipady=9)
        load()

    @staticmethod
    def _delete_selected(tree, action, reload_action):
        for iid in tree.selection(): action(int(iid))
        reload_action()

    def build_sales_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("employee", "total", "cash", "change", "date"), show="tree headings")
        tree.pack(fill="both", expand=True); tree.heading("#0", text="Sale")
        for col, text in [("employee", "Employee"), ("total", "Total"), ("cash", "Cash"), ("change", "Change"), ("date", "Date")]: tree.heading(col, text=text)
        for sale in DB.sales(): tree.insert("", "end", text=f"#{sale['id']}", values=(sale["employee_name"], money(sale["total_cents"]), money(sale["cash_cents"]), money(sale["change_cents"]), sale["created_at"]))

    def build_printers_tab(self, parent):
        info = ttk.Label(parent, text="Add network/IP receipt printers, Linux/CUPS queues, Windows printers, or a test file printer. 80 mm uses 48 characters per line; 58 mm uses 32.", wraplength=950)
        info.pack(anchor="w", pady=(0, 8))
        tree = ttk.Treeview(parent, columns=("type", "connection", "paper", "default", "active"), show="tree headings")
        tree.pack(fill="both", expand=True)
        for col, text in [("#0", "Name"), ("type", "Type"), ("connection", "Connection"), ("paper", "Paper"), ("default", "Default"), ("active", "Active")]: tree.heading(col, text=text)
        def connection(row):
            if row["printer_type"] == "network": return f"{row['host']}:{row['port']}"
            if row["printer_type"] in ("system", "cups", "windows"): return row["queue_name"] or "Default queue"
            return row["file_path"]
        def load():
            tree.delete(*tree.get_children())
            for row in DB.printers(): tree.insert("", "end", iid=str(row["id"]), text=row["name"], values=(row["printer_type"], connection(row), f"{row['paper_width_mm']} mm", "Yes" if row["is_default"] else "No", "Yes" if row["active"] else "No"))
        def edit(new=False):
            pid = None if new or not tree.selection() else int(tree.selection()[0])
            row = DB.printer_by_id(pid) if pid else None
            win = tk.Toplevel(self); win.title("Receipt Printer"); win.geometry("760x620"); win.transient(self); win.grab_set(); win.configure(padx=14, pady=14)
            variables = {
                "name": tk.StringVar(value=row["name"] if row else "Receipt Printer"),
                "type": tk.StringVar(value=row["printer_type"] if row else "network"),
                "host": tk.StringVar(value=row["host"] if row else ""),
                "port": tk.StringVar(value=str(row["port"] if row else 9100)),
                "queue": tk.StringVar(value=row["queue_name"] if row else ""),
                "file": tk.StringVar(value=row["file_path"] if row else str(DATA_DIR / "test-receipt.txt")),
                "paper": tk.StringVar(value=str(row["paper_width_mm"] if row else 80)),
                "cut": tk.BooleanVar(value=bool(row["auto_cut"]) if row else True),
                "default": tk.BooleanVar(value=bool(row["is_default"]) if row else not DB.printers()),
                "active": tk.BooleanVar(value=bool(row["active"]) if row else True),
            }
            fields = [("Printer name", "name"), ("IP address / hostname", "host"), ("Port", "port"), ("System/Windows queue name", "queue"), ("Test file path", "file")]
            for r, (label, key) in enumerate(fields):
                ttk.Label(win, text=label).grid(row=r, column=0, sticky="w", pady=6)
                ttk.Entry(win, textvariable=variables[key], font=("DejaVu Sans", 14)).grid(row=r, column=1, sticky="ew", padx=6, pady=6, ipady=7)
                is_num = key == "port"
                ttk.Button(win, text="⌨", command=lambda k=key, n=is_num: self._edit_var(variables[k], n)).grid(row=r, column=2, padx=4, pady=6, ipady=7)
            ttk.Label(win, text="Printer type").grid(row=5, column=0, sticky="w", pady=6)
            ttk.Combobox(win, textvariable=variables["type"], state="readonly", values=("network", "system", "cups", "windows", "file")).grid(row=5, column=1, sticky="ew", padx=6, pady=6)
            ttk.Label(win, text="Paper width").grid(row=6, column=0, sticky="w", pady=6)
            ttk.Combobox(win, textvariable=variables["paper"], state="readonly", values=("80", "58")).grid(row=6, column=1, sticky="ew", padx=6, pady=6)
            ttk.Checkbutton(win, text="Auto-cut after receipt", variable=variables["cut"]).grid(row=7, column=0, columnspan=2, sticky="w", pady=6)
            ttk.Checkbutton(win, text="Use as default printer", variable=variables["default"]).grid(row=8, column=0, columnspan=2, sticky="w", pady=6)
            ttk.Checkbutton(win, text="Printer enabled", variable=variables["active"]).grid(row=9, column=0, columnspan=2, sticky="w", pady=6)
            win.columnconfigure(1, weight=1)
            def save():
                try:
                    DB.save_printer(pid, variables["name"].get().strip(), variables["type"].get(), variables["host"].get().strip(), int(variables["port"].get() or 9100), variables["queue"].get().strip(), variables["file"].get().strip(), int(variables["paper"].get()), variables["cut"].get(), variables["default"].get(), variables["active"].get())
                    win.destroy(); load()
                except Exception as exc: messagebox.showerror("Printer", str(exc), parent=win)
            ttk.Button(win, text="SAVE PRINTER", command=save).grid(row=10, column=0, columnspan=3, sticky="ew", pady=14, ipady=12)
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
        ttk.Button(parent, text="Exit POS OS", command=self.destroy).pack(anchor="w", fill="x", pady=5, ipady=8)

    def backup_database(self):
        destination = DATA_DIR / "backups"
        destination.mkdir(parents=True, exist_ok=True)
        filename = destination / "posos-manual-backup.db"
        shutil.copy2(DB.path, filename)
        messagebox.showinfo("Backup", f"Backup saved to {filename}")

    def manager_exit(self):
        if self.current_user and self.current_user["role"] == "manager": self.destroy()


def main():
    POSOS().mainloop()
