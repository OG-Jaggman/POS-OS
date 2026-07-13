from __future__ import annotations

import os
import shutil
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

from .db import Database
from .printer import PrinterError, build_receipt_text, open_cash_drawer, print_receipt
from .security import hash_pin, verify_pin
from .updater import check_latest

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
        self.shifted = False
        self.letter_buttons: list[ttk.Button] = []
        self.title(title)
        self.transient(parent)
        self.grab_set()
        self.attributes("-topmost", True)
        self.geometry("760x620")
        self.configure(padx=18, pady=18)

        ttk.Label(self, text=prompt, font=("DejaVu Sans", 20, "bold"), wraplength=700).pack(pady=(0, 12))
        self.value = tk.StringVar(value=initial)
        self.entry = ttk.Entry(
            self,
            textvariable=self.value,
            show="•" if secret else "",
            justify="center",
            font=("DejaVu Sans", 25),
        )
        self.entry.pack(fill="x", ipady=10, pady=(0, 14))
        self.entry.focus_set()

        keypad = ttk.Frame(self)
        keypad.pack(fill="both", expand=True)
        if numeric:
            keys = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["Clear", "0", "⌫"]]
            if decimal:
                keys[-1] = ["Clear", "0", ".", "⌫"]
            for row_index, row in enumerate(keys):
                for column_index, key in enumerate(row):
                    ttk.Button(keypad, text=key, command=lambda k=key: self.press(k)).grid(
                        row=row_index,
                        column=column_index,
                        sticky="nsew",
                        padx=5,
                        pady=5,
                        ipady=15,
                    )
                    keypad.columnconfigure(column_index, weight=1)
                keypad.rowconfigure(row_index, weight=1)
        else:
            for row in ("1234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm"):
                holder = ttk.Frame(keypad)
                holder.pack(fill="both", expand=True)
                for key in row:
                    button = ttk.Button(holder, text=key, command=lambda k=key: self.press(k))
                    button.pack(side="left", fill="both", expand=True, padx=2, pady=3)
                    if key.isalpha():
                        self.letter_buttons.append(button)
            bottom = ttk.Frame(keypad)
            bottom.pack(fill="both", expand=True)
            self.shift_button = ttk.Button(bottom, text="Shift ⇧", command=self.toggle_shift)
            self.shift_button.pack(side="left", fill="both", expand=True, padx=3)
            ttk.Button(bottom, text="Space", command=lambda: self.press(" ")).pack(side="left", fill="both", expand=True, padx=3)
            ttk.Button(bottom, text="⌫", command=lambda: self.press("⌫")).pack(side="left", fill="both", expand=True, padx=3)
            ttk.Button(bottom, text="Clear", command=lambda: self.press("Clear")).pack(side="left", fill="both", expand=True, padx=3)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="left", fill="x", expand=True, padx=4, ipady=12)
        ttk.Button(buttons, text="OK", command=self.ok).pack(side="left", fill="x", expand=True, padx=4, ipady=12)
        self.bind("<Return>", lambda _event: self.ok())
        self.bind("<Escape>", lambda _event: self.cancel())

    def toggle_shift(self):
        self.shifted = not self.shifted
        for button in self.letter_buttons:
            current = str(button.cget("text"))
            button.configure(text=current.upper() if self.shifted else current.lower())
        self.shift_button.configure(text="SHIFT ⇧" if self.shifted else "Shift ⇧")

    def press(self, key):
        if key == "Clear":
            self.value.set("")
        elif key == "⌫":
            self.value.set(self.value.get()[:-1])
        elif key == "." and "." in self.value.get():
            return
        else:
            if key.isalpha():
                key = key.upper() if self.shifted else key.lower()
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
            if key == "Clear":
                value.set("")
            elif key == "⌫":
                value.set(value.get()[:-1])
            else:
                value.set(value.get() + key)

        def sign_in(*_):
            for employee in DB.employee_by_pin_candidates():
                if verify_pin(value.get(), employee["pin_hash"]):
                    self.current_user = employee
                    self.register_screen()
                    return
            value.set("")
            messagebox.showerror("Login failed", "Incorrect or disabled employee PIN.")

        keypad = ttk.Frame(frame)
        keypad.pack(fill="both", expand=True)
        for row_index, row in enumerate([["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["Clear", "0", "⌫"]]):
            for column_index, key in enumerate(row):
                ttk.Button(keypad, text=key, command=lambda k=key: press(k)).grid(
                    row=row_index,
                    column=column_index,
                    sticky="nsew",
                    padx=5,
                    pady=5,
                    ipadx=18,
                    ipady=12,
                )
                keypad.columnconfigure(column_index, weight=1)
            keypad.rowconfigure(row_index, weight=1)
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
        ttk.Button(
            search_row,
            text="⌨",
            command=lambda: self._set_from_dialog(search, self.ask_text("Search", "Product name or barcode", search.get())),
        ).pack(side="left", padx=(5, 0), ipadx=10, ipady=7)

        grid = ttk.Frame(left)
        grid.pack(fill="both", expand=True)

        def refresh(*_):
            for widget in grid.winfo_children():
                widget.destroy()
            query = search.get().lower().strip()
            items = [item for item in DB.items(True) if query in item["name"].lower() or query in (item["barcode"] or "").lower()]
            for index, item in enumerate(items[:60]):
                ttk.Button(
                    grid,
                    text=f"{item['name']}\n{money(item['price_cents'])}",
                    command=lambda selected=item: self.add_item(selected),
                ).grid(row=index // 4, column=index % 4, sticky="nsew", padx=3, pady=3, ipady=12)
            for column in range(4):
                grid.columnconfigure(column, weight=1)

        search.trace_add("write", refresh)
        refresh()
        entry.bind("<Return>", lambda _event: (self.scan_or_search(search.get()), search.set("")))

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
        if result is not None:
            variable.set(result)

    def scan_or_search(self, text):
        item = DB.item_by_barcode(text.strip())
        if item:
            self.add_item(item)

    def add_item(self, item):
        key = item["id"]
        self.cart.setdefault(key, {"id": key, "name": item["name"], "price_cents": item["price_cents"], "qty": 0})
        self.cart[key]["qty"] += 1
        self.refresh_cart()

    def refresh_cart(self):
        for item_id in self.cart_tree.get_children():
            self.cart_tree.delete(item_id)
        total = 0
        for key, line in self.cart.items():
            line_total = line["qty"] * line["price_cents"]
            total += line_total
            self.cart_tree.insert("", "end", iid=str(key), text=line["name"], values=(line["qty"], money(line["price_cents"]), money(line_total)))
        self.total_label.config(text=f"Total: {money(total)}")

    def change_quantity(self, amount):
        for item_id in self.cart_tree.selection():
            key = int(item_id)
            self.cart[key]["qty"] += amount
            if self.cart[key]["qty"] <= 0:
                self.cart.pop(key, None)
        self.refresh_cart()

    def remove_selected(self):
        for item_id in self.cart_tree.selection():
            self.cart.pop(int(item_id), None)
        self.refresh_cart()

    def clear_sale(self):
        if self.cart and messagebox.askyesno("Clear sale", "Remove every item from this sale?"):
            self.cart.clear()
            self.refresh_cart()

    def cash_payment(self):
        if not self.cart:
            return
        lines = list(self.cart.values())
        total = sum(line["qty"] * line["price_cents"] for line in lines)
        raw = self.ask_number("Cash payment", f"Total: {money(total)}\nCash received", decimal=True)
        try:
            cash = parse_money(raw or "")
        except Exception:
            messagebox.showerror("Cash payment", "Enter a valid amount.")
            return
        if cash < total:
            messagebox.showerror("Cash payment", "Cash received is less than the total.")
            return

        change = cash - total
        sale_id, created_at = DB.complete_sale(self.current_user["id"], lines, total, cash, change)
        default = DB.default_printer()
        warnings = []
        if default:
            printer = dict(default)
            try:
                receipt = build_receipt_text(
                    DB.get_setting("store_name", "POS OS"),
                    sale_id,
                    self.current_user["name"],
                    created_at,
                    lines,
                    total,
                    cash,
                    change,
                    printer["paper_width_mm"],
                )
                print_receipt(printer, receipt)
            except PrinterError as exc:
                warnings.append(f"Receipt did not print: {exc}")
            if printer.get("drawer_enabled"):
                try:
                    open_cash_drawer(printer)
                except PrinterError as exc:
                    warnings.append(f"Cash drawer did not open: {exc}")

        message = f"Change due: {money(change)}"
        if warnings:
            message += "\n\n" + "\n".join(warnings)
            messagebox.showwarning("Sale complete", message)
        else:
            messagebox.showinfo("Sale complete", message)
        self.register_screen()

    def manager_screen(self):
        if self.current_user["role"] != "manager":
            return
        self.clear()
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Manager Settings", font=("DejaVu Sans", 22, "bold")).pack(side="left")
        ttk.Button(top, text="Back to register", command=self.register_screen).pack(side="right", ipady=6)
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        names = ("Items", "Employees", "Sales", "Printers & Drawer", "System")
        tabs = {name: ttk.Frame(notebook, padding=8) for name in names}
        for name, tab in tabs.items():
            notebook.add(tab, text=name)
        self.build_items_tab(tabs["Items"])
        self.build_employees_tab(tabs["Employees"])
        self.build_sales_tab(tabs["Sales"])
        self.build_printers_tab(tabs["Printers & Drawer"])
        self.build_system_tab(tabs["System"])

    def build_items_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("barcode", "price", "stock", "category"), show="tree headings")
        for column, text in [("#0", "Item"), ("barcode", "Barcode"), ("price", "Price"), ("stock", "Stock"), ("category", "Category")]:
            tree.heading(column, text=text)
        tree.pack(fill="both", expand=True)

        def load():
            tree.delete(*tree.get_children())
            for row in DB.items(False):
                tree.insert("", "end", iid=str(row["id"]), text=row["name"], values=(row["barcode"], money(row["price_cents"]), row["stock_qty"], row["category"]))

        def edit(new=False):
            row = None if new or not tree.selection() else DB.item_by_id(int(tree.selection()[0]))
            name = self.ask_text("Item", "Item name", row["name"] if row else "")
            if not name:
                return
            barcode = self.ask_text("Item", "Barcode", row["barcode"] if row else "")
            price = self.ask_number("Item", "Price", money(row["price_cents"]) if row else "0.00", decimal=True)
            category = self.ask_text("Item", "Category", row["category"] if row else "General")
            stock = self.ask_number("Item", "Inventory quantity", str(row["stock_qty"] if row else 0))
            low = self.ask_number("Item", "Low-stock level", str(row["low_stock"] if row else 0))
            try:
                DB.save_item(row["id"] if row else None, name.strip(), (barcode or "").strip(), parse_money(price), (category or "General").strip(), int(stock), int(low), True)
                load()
            except Exception as exc:
                messagebox.showerror("Item", str(exc))

        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(8, 0))
        for text, command in [("Add item", lambda: edit(True)), ("Edit selected", edit), ("Delete selected", lambda: self._delete_selected(tree, DB.delete_item, load))]:
            ttk.Button(bar, text=text, command=command).pack(side="left", fill="x", expand=True, ipady=9)
        load()

    def build_employees_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("role", "active"), show="tree headings")
        tree.heading("#0", text="Employee")
        tree.heading("role", text="Role")
        tree.heading("active", text="Active")
        tree.pack(fill="both", expand=True)

        def load():
            tree.delete(*tree.get_children())
            for row in DB.employees():
                tree.insert("", "end", iid=str(row["id"]), text=row["name"], values=(row["role"], "Yes" if row["active"] else "No"))

        def edit(new=False):
            row = None if new or not tree.selection() else DB.employee_by_id(int(tree.selection()[0]))
            name = self.ask_text("Employee", "Employee name", row["name"] if row else "")
            if not name:
                return
            role = self.ask_text("Employee", "Role: cashier or manager", row["role"] if row else "cashier")
            role = (role or "").lower().strip()
            if role not in ("cashier", "manager"):
                messagebox.showerror("Role", "Role must be cashier or manager.")
                return
            pin = self.ask_number("Employee", "New PIN (leave blank to keep current)", secret=True)
            try:
                pin_hash = hash_pin(pin) if pin else None
                employee_id = row["id"] if row else None
                if employee_id:
                    DB.update_employee(employee_id, name.strip(), role, True, pin_hash)
                elif pin_hash:
                    DB.add_employee(name.strip(), pin_hash, role)
                else:
                    raise ValueError("A PIN is required for a new employee.")
                load()
            except Exception as exc:
                messagebox.showerror("Employee", str(exc))

        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(8, 0))
        for text, command in [("Add employee", lambda: edit(True)), ("Edit selected", edit), ("Delete selected", lambda: self._delete_selected(tree, DB.delete_employee, load))]:
            ttk.Button(bar, text=text, command=command).pack(side="left", fill="x", expand=True, ipady=9)
        load()

    def build_sales_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("employee", "total", "cash", "change", "time"), show="headings")
        for column in ("employee", "total", "cash", "change", "time"):
            tree.heading(column, text=column.title())
        tree.pack(fill="both", expand=True)
        for row in DB.sales():
            tree.insert("", "end", values=(row["employee_name"], money(row["total_cents"]), money(row["cash_cents"]), money(row["change_cents"]), row["created_at"]))

    def build_printers_tab(self, parent):
        tree = ttk.Treeview(parent, columns=("type", "destination", "paper", "drawer", "default"), show="tree headings")
        for column, text in [("#0", "Printer"), ("type", "Type"), ("destination", "Destination"), ("paper", "Paper"), ("drawer", "Drawer"), ("default", "Default")]:
            tree.heading(column, text=text)
        tree.pack(fill="both", expand=True)

        def destination(row):
            if row["printer_type"] == "network":
                return f"{row['host']}:{row['port']}"
            if row["printer_type"] in ("system", "cups", "windows"):
                return row["queue_name"] or "Default queue"
            return row["file_path"]

        def load():
            tree.delete(*tree.get_children())
            for row in DB.printers():
                tree.insert(
                    "",
                    "end",
                    iid=str(row["id"]),
                    text=row["name"],
                    values=(row["printer_type"], destination(row), f"{row['paper_width_mm']} mm", "Enabled" if row["drawer_enabled"] else "Off", "Yes" if row["is_default"] else ""),
                )

        def edit(new=False):
            row = None if new or not tree.selection() else DB.printer_by_id(int(tree.selection()[0]))
            win = tk.Toplevel(self)
            win.title("Printer & Cash Drawer")
            win.transient(self)
            win.grab_set()
            win.geometry("800x720")
            outer = ttk.Frame(win, padding=16)
            outer.pack(fill="both", expand=True)
            defaults = {
                "name": row["name"] if row else "Receipt Printer",
                "type": row["printer_type"] if row else "network",
                "host": row["host"] if row else "",
                "port": str(row["port"] if row else 9100),
                "queue": row["queue_name"] if row else "",
                "file": row["file_path"] if row else str(DATA_DIR / "receipts" / "test-receipt.txt"),
                "paper": str(row["paper_width_mm"] if row else 80),
                "drawer_pin": str(row["drawer_pin"] if row else 0),
                "drawer_on": str(row["drawer_on_ms"] if row else 120),
                "drawer_off": str(row["drawer_off_ms"] if row else 240),
            }
            variables = {key: tk.StringVar(value=value) for key, value in defaults.items()}
            fields = [
                ("Printer name", "name", False),
                ("IP address / hostname", "host", False),
                ("Port", "port", True),
                ("System/Windows queue name", "queue", False),
                ("Test file path", "file", False),
                ("Drawer pulse ON (ms)", "drawer_on", True),
                ("Drawer pulse OFF (ms)", "drawer_off", True),
            ]
            for index, (label, key, numeric) in enumerate(fields):
                ttk.Label(outer, text=label).grid(row=index, column=0, sticky="w", pady=5)
                ttk.Entry(outer, textvariable=variables[key]).grid(row=index, column=1, sticky="ew", padx=6, pady=5, ipady=5)
                ttk.Button(outer, text="⌨", command=lambda variable=variables[key], number=numeric: self._edit_var(variable, number)).grid(row=index, column=2, pady=5)

            row_index = len(fields)
            ttk.Label(outer, text="Printer type").grid(row=row_index, column=0, sticky="w", pady=5)
            ttk.Combobox(outer, textvariable=variables["type"], state="readonly", values=("network", "system", "cups", "windows", "file")).grid(row=row_index, column=1, sticky="ew", padx=6, pady=5)
            row_index += 1
            ttk.Label(outer, text="Receipt paper width").grid(row=row_index, column=0, sticky="w", pady=5)
            ttk.Combobox(outer, textvariable=variables["paper"], state="readonly", values=("80", "58")).grid(row=row_index, column=1, sticky="ew", padx=6, pady=5)
            row_index += 1
            ttk.Label(outer, text="Drawer connector pin").grid(row=row_index, column=0, sticky="w", pady=5)
            ttk.Combobox(outer, textvariable=variables["drawer_pin"], state="readonly", values=("0", "1")).grid(row=row_index, column=1, sticky="ew", padx=6, pady=5)
            row_index += 1

            auto_cut = tk.BooleanVar(value=bool(row["auto_cut"]) if row else True)
            drawer_enabled = tk.BooleanVar(value=bool(row["drawer_enabled"]) if row else True)
            default = tk.BooleanVar(value=bool(row["is_default"]) if row else True)
            ttk.Checkbutton(outer, text="Send auto-cut command", variable=auto_cut).grid(row=row_index, column=0, columnspan=2, sticky="w", pady=6)
            row_index += 1
            ttk.Checkbutton(outer, text="Open cash drawer after cash payments", variable=drawer_enabled).grid(row=row_index, column=0, columnspan=2, sticky="w", pady=6)
            row_index += 1
            ttk.Checkbutton(outer, text="Use as default printer/drawer", variable=default).grid(row=row_index, column=0, columnspan=2, sticky="w", pady=6)
            row_index += 1
            ttk.Label(outer, text="Network printers normally use raw ESC/POS on TCP port 9100. Most drawers use pin 0 with a 120/240 ms pulse.", wraplength=700).grid(row=row_index, column=0, columnspan=3, sticky="w", pady=10)
            row_index += 1
            outer.columnconfigure(1, weight=1)

            def save():
                try:
                    DB.save_printer(
                        row["id"] if row else None,
                        variables["name"].get().strip(),
                        variables["type"].get(),
                        variables["host"].get().strip(),
                        int(variables["port"].get() or 9100),
                        variables["queue"].get().strip(),
                        variables["file"].get().strip(),
                        int(variables["paper"].get()),
                        auto_cut.get(),
                        drawer_enabled.get(),
                        int(variables["drawer_pin"].get()),
                        int(variables["drawer_on"].get()),
                        int(variables["drawer_off"].get()),
                        default.get(),
                        True,
                    )
                    win.destroy()
                    load()
                except Exception as exc:
                    messagebox.showerror("Printer & Drawer", str(exc), parent=win)

            ttk.Button(outer, text="Save printer & drawer", command=save).grid(row=row_index, column=0, columnspan=3, sticky="ew", ipady=12)

        def selected_printer():
            if not tree.selection():
                messagebox.showinfo("Printers & Drawer", "Select a printer first.")
                return None
            return dict(DB.printer_by_id(int(tree.selection()[0])))

        def test_receipt():
            printer = selected_printer()
            if not printer:
                return
            lines = [
                {"name": "Test Item", "qty": 1, "price_cents": 199},
                {"name": "Second Test Item", "qty": 2, "price_cents": 125},
            ]
            total = 449
            cash = 500
            sample = build_receipt_text(
                DB.get_setting("store_name", "POS OS"),
                123,
                self.current_user["name"],
                datetime.now().isoformat(timespec="seconds"),
                lines,
                total,
                cash,
                cash - total,
                printer["paper_width_mm"],
            )
            try:
                print_receipt(printer, sample)
                messagebox.showinfo("Test receipt", "A full test receipt was sent exactly like a normal sale receipt.")
            except PrinterError as exc:
                messagebox.showerror("Test receipt failed", str(exc))

        def open_drawer():
            printer = selected_printer()
            if not printer:
                return
            try:
                open_cash_drawer(printer, force=True)
                messagebox.showinfo("Cash drawer", "Open-drawer pulse sent.")
            except PrinterError as exc:
                messagebox.showerror("Cash drawer failed", str(exc))

        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(8, 0))
        buttons = [
            ("Add printer", lambda: edit(True)),
            ("Edit selected", edit),
            ("Print Test Receipt", test_receipt),
            ("Open Drawer", open_drawer),
            ("Delete selected", lambda: self._delete_selected(tree, DB.delete_printer, load)),
        ]
        for text, command in buttons:
            ttk.Button(bar, text=text, command=command).pack(side="left", fill="x", expand=True, ipady=9, padx=2)
        load()

    def _delete_selected(self, tree, delete_function, reload_function):
        selection = tree.selection()
        if not selection:
            return
        if not messagebox.askyesno("Delete", "Delete the selected entry?"):
            return
        try:
            delete_function(int(selection[0]))
            reload_function()
        except Exception as exc:
            messagebox.showerror("Delete failed", str(exc))

    def _edit_var(self, variable, numeric=False):
        result = self.ask_number("Enter value", "Enter value", variable.get()) if numeric else self.ask_text("Enter value", "Enter value", variable.get())
        if result is not None:
            variable.set(result)

    def build_system_tab(self, parent):
        ttk.Label(parent, text="POS OS contains no tax calculation. Item prices are final prices.", font=("DejaVu Sans", 14, "bold")).pack(anchor="w", pady=8)
        store = ttk.Frame(parent)
        store.pack(fill="x", pady=8)
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
        return


def main():
    POSOS().mainloop()
