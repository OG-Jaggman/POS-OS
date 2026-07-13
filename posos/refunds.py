from __future__ import annotations

import sqlite3
from tkinter import messagebox, ttk

from .db import Database
from .printer import PrinterError, open_cash_drawer


def _ensure_refund_columns(db: Database) -> None:
    columns = {row["name"] for row in db.conn.execute("PRAGMA table_info(sales)")}
    additions = {
        "refunded_at": "TEXT",
        "refunded_by": "INTEGER",
        "refund_reason": "TEXT NOT NULL DEFAULT ''",
    }
    for name, definition in additions.items():
        if name not in columns:
            db.conn.execute(f"ALTER TABLE sales ADD COLUMN {name} {definition}")
    db.conn.commit()


def refund_sale(db: Database, sale_id: int, manager_id: int, reason: str = "") -> int:
    """Refund a complete sale once and restore its inventory."""
    _ensure_refund_columns(db)
    sale = db.conn.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    if not sale:
        raise ValueError("That sale no longer exists.")
    if sale["refunded_at"]:
        raise ValueError("That sale has already been refunded.")

    lines = db.conn.execute(
        "SELECT item_id,quantity FROM sale_lines WHERE sale_id=?", (sale_id,)
    ).fetchall()

    try:
        db.conn.execute("BEGIN IMMEDIATE")
        for line in lines:
            if line["item_id"]:
                db.conn.execute(
                    "UPDATE items SET stock_qty=stock_qty+?,updated_at=? WHERE id=?",
                    (line["quantity"], db.now(), line["item_id"]),
                )
        changed = db.conn.execute(
            "UPDATE sales SET refunded_at=?,refunded_by=?,refund_reason=? "
            "WHERE id=? AND refunded_at IS NULL",
            (db.now(), manager_id, reason.strip(), sale_id),
        ).rowcount
        if changed != 1:
            raise ValueError("That sale was already refunded.")
        db.conn.commit()
    except Exception:
        db.conn.rollback()
        raise

    return int(sale["total_cents"])


def install_sales_refund_controls(root, parent) -> None:
    """Upgrade the existing Manager > Sales tab with full-sale refunds."""
    from .app import DB, money

    _ensure_refund_columns(DB)
    trees = [widget for widget in parent.winfo_children() if isinstance(widget, ttk.Treeview)]
    if not trees or getattr(parent, "_posos_refund_controls", False):
        return
    parent._posos_refund_controls = True
    tree = trees[0]
    tree.configure(columns=("employee", "total", "cash", "change", "time", "status"))
    for column, title in (
        ("employee", "Employee"),
        ("total", "Total"),
        ("cash", "Cash"),
        ("change", "Change"),
        ("time", "Time"),
        ("status", "Status"),
    ):
        tree.heading(column, text=title)
    tree.column("status", width=120, anchor="center")

    def load() -> None:
        tree.delete(*tree.get_children())
        rows = DB.conn.execute(
            "SELECT sales.*,employees.name employee_name "
            "FROM sales JOIN employees ON employees.id=sales.employee_id "
            "ORDER BY sales.id DESC LIMIT 100"
        ).fetchall()
        for row in rows:
            status = "REFUNDED" if row["refunded_at"] else "Completed"
            tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["employee_name"],
                    money(row["total_cents"]),
                    money(row["cash_cents"]),
                    money(row["change_cents"]),
                    row["created_at"],
                    status,
                ),
            )

    def refund_selected() -> None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Refund sale", "Select a sale first.")
            return
        sale_id = int(selection[0])
        sale = DB.conn.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
        if not sale:
            messagebox.showerror("Refund sale", "That sale could not be found.")
            return
        if sale["refunded_at"]:
            messagebox.showinfo("Refund sale", "That sale has already been refunded.")
            return
        if not messagebox.askyesno(
            "Refund sale",
            f"Refund sale #{sale_id} for {money(sale['total_cents'])}?\n\n"
            "This restores the sold inventory and cannot be repeated.",
        ):
            return
        reason = root.ask_text("Refund reason", "Reason for refund (optional)") or ""
        try:
            amount = refund_sale(DB, sale_id, root.current_user["id"], reason)
            drawer_warning = ""
            printer = DB.default_printer()
            if printer and printer["drawer_enabled"]:
                try:
                    open_cash_drawer(dict(printer), force=True)
                except PrinterError as exc:
                    drawer_warning = f"\n\nCash drawer did not open: {exc}"
            load()
            messagebox.showinfo(
                "Refund complete",
                f"Sale #{sale_id} was refunded for {money(amount)}.\n"
                "Inventory was restored." + drawer_warning,
            )
        except (ValueError, sqlite3.Error) as exc:
            messagebox.showerror("Refund failed", str(exc))

    bar = ttk.Frame(parent)
    bar.pack(fill="x", pady=(8, 0))
    ttk.Button(
        bar,
        text="Refund selected sale",
        command=refund_selected,
    ).pack(fill="x", expand=True, ipady=10)
    ttk.Label(
        parent,
        text="Refunds are manager-only, restore inventory, and keep the original sale for records.",
        wraplength=850,
    ).pack(anchor="w", pady=(8, 0))
    load()


def patch_sales_tab() -> None:
    """Wrap POSOS.build_sales_tab so refunds appear without rewriting app.py."""
    from .app import POSOS

    if getattr(POSOS, "_posos_refund_patch", False):
        return
    original = POSOS.build_sales_tab

    def wrapped(self, parent):
        original(self, parent)
        install_sales_refund_controls(self, parent)

    POSOS.build_sales_tab = wrapped
    POSOS._posos_refund_patch = True
