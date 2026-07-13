from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, ttk


def _ensure_tables(db) -> None:
    db.conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS saved_orders (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            employee_id INTEGER NOT NULL,
            cart_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(employee_id) REFERENCES employees(id)
        );
        """
    )
    db.conn.commit()


def _save_order(db, employee_id: int, name: str, cart: dict) -> int:
    _ensure_tables(db)
    payload = json.dumps(list(cart.values()), separators=(",", ":"))
    cursor = db.conn.execute(
        "INSERT INTO saved_orders(name,employee_id,cart_json,created_at) VALUES(?,?,?,?)",
        (name.strip() or "Saved order", employee_id, payload, db.now()),
    )
    db.conn.commit()
    return int(cursor.lastrowid)


def _saved_orders(db):
    _ensure_tables(db)
    return db.conn.execute(
        "SELECT saved_orders.*,employees.name employee_name "
        "FROM saved_orders JOIN employees ON employees.id=saved_orders.employee_id "
        "ORDER BY saved_orders.id DESC"
    ).fetchall()


def _load_order(db, order_id: int) -> dict:
    _ensure_tables(db)
    row = db.conn.execute("SELECT * FROM saved_orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        raise ValueError("That saved order no longer exists.")
    try:
        lines = json.loads(row["cart_json"])
    except Exception as exc:
        raise ValueError("The saved order data is damaged.") from exc
    cart: dict[int, dict] = {}
    for line in lines:
        item_id = int(line["id"])
        cart[item_id] = {
            "id": item_id,
            "name": str(line["name"]),
            "price_cents": int(line["price_cents"]),
            "qty": int(line["qty"]),
        }
    return cart


def _delete_order(db, order_id: int) -> None:
    db.conn.execute("DELETE FROM saved_orders WHERE id=?", (order_id,))
    db.conn.commit()


def patch_register_saved_orders() -> None:
    from .app import DB, POSOS, money

    if getattr(POSOS, "_posos_saved_orders_patch", False):
        return

    _ensure_tables(DB)
    original_register_screen = POSOS.register_screen

    def open_saved_orders(self) -> None:
        window = tk.Toplevel(self)
        window.title("Saved Orders")
        window.transient(self)
        window.grab_set()
        window.attributes("-topmost", True)
        window.geometry("850x560")

        outer = ttk.Frame(window, padding=14)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Saved Orders", font=("DejaVu Sans", 22, "bold")).pack(anchor="w", pady=(0, 10))

        tree = ttk.Treeview(
            outer,
            columns=("employee", "items", "total", "created"),
            show="tree headings",
            height=15,
        )
        tree.heading("#0", text="Order name")
        tree.heading("employee", text="Saved by")
        tree.heading("items", text="Items")
        tree.heading("total", text="Total")
        tree.heading("created", text="Saved at")
        tree.column("#0", width=220)
        tree.column("employee", width=140)
        tree.column("items", width=70, anchor="center")
        tree.column("total", width=110, anchor="e")
        tree.column("created", width=180)
        tree.pack(fill="both", expand=True)

        def refresh() -> None:
            tree.delete(*tree.get_children())
            for row in _saved_orders(DB):
                try:
                    lines = json.loads(row["cart_json"])
                    item_count = sum(int(line.get("qty", 0)) for line in lines)
                    total = sum(int(line.get("qty", 0)) * int(line.get("price_cents", 0)) for line in lines)
                except Exception:
                    item_count = 0
                    total = 0
                tree.insert(
                    "",
                    "end",
                    iid=str(row["id"]),
                    text=row["name"],
                    values=(row["employee_name"], item_count, money(total), row["created_at"]),
                )

        def selected_id() -> int | None:
            selection = tree.selection()
            if not selection:
                messagebox.showinfo("Saved Orders", "Select a saved order first.", parent=window)
                return None
            return int(selection[0])

        def restore() -> None:
            order_id = selected_id()
            if order_id is None:
                return
            if self.cart and not messagebox.askyesno(
                "Replace current order",
                "Replace the items currently on the register with this saved order?",
                parent=window,
            ):
                return
            try:
                self.cart = _load_order(DB, order_id)
                _delete_order(DB, order_id)
                self.refresh_cart()
                window.destroy()
                messagebox.showinfo("Saved Orders", "The saved order is back on the register.")
            except ValueError as exc:
                messagebox.showerror("Saved Orders", str(exc), parent=window)

        def delete() -> None:
            order_id = selected_id()
            if order_id is None:
                return
            if not messagebox.askyesno(
                "Delete saved order",
                "Permanently delete the selected saved order?",
                parent=window,
            ):
                return
            _delete_order(DB, order_id)
            refresh()

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(10, 0))
        ttk.Button(buttons, text="Restore selected", command=restore).pack(side="left", fill="x", expand=True, padx=3, ipady=10)
        ttk.Button(buttons, text="Delete selected", command=delete).pack(side="left", fill="x", expand=True, padx=3, ipady=10)
        ttk.Button(buttons, text="Close", command=window.destroy).pack(side="left", fill="x", expand=True, padx=3, ipady=10)
        refresh()

    def save_current_order(self) -> None:
        if not self.cart:
            messagebox.showinfo("Save Order", "There are no items in the current order.")
            return
        default_name = f"Order {DB.now().replace('T', ' ')}"
        name = self.ask_text("Save Order", "Name for this order", default_name)
        if name is None:
            return
        order_id = _save_order(DB, self.current_user["id"], name, self.cart)
        self.cart = {}
        self.refresh_cart()
        messagebox.showinfo("Save Order", f"Order #{order_id} was saved and the register was cleared.")

    def wrapped_register_screen(self):
        original_register_screen(self)
        children = self.winfo_children()
        if not children:
            return
        top = children[0]
        if not isinstance(top, ttk.Frame):
            return
        ttk.Button(top, text="Saved Orders", command=lambda: open_saved_orders(self)).pack(
            side="right", padx=4, ipadx=8, ipady=6
        )
        ttk.Button(top, text="Save Order", command=lambda: save_current_order(self)).pack(
            side="right", padx=4, ipadx=8, ipady=6
        )

    POSOS.register_screen = wrapped_register_screen
    POSOS.open_saved_orders = open_saved_orders
    POSOS.save_current_order = save_current_order
    POSOS._posos_saved_orders_patch = True
