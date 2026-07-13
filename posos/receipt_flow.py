from __future__ import annotations

import tkinter as tk
from tkinter import messagebox


def patch_post_transaction_receipts() -> None:
    """Always print the cashier copy, then ask about the customer copy.

    The payment window's old pre-transaction receipt checkbox is hidden. The
    receipt question is shown only after the sale has already been committed.
    """
    from .app import DB, POSOS
    from . import giftcards
    from .printer import PrinterError, print_receipt

    if getattr(POSOS, "_posos_post_transaction_receipts_patch", False):
        return

    def print_after_sale(
        db,
        sale_id,
        employee,
        created,
        lines,
        total,
        payment,
        _old_customer_copy_value,
        cash=0,
        change=0,
        last4="",
        remaining=0,
    ):
        printer_row = db.default_printer()
        if not printer_row:
            return ["No default receipt printer is configured."]

        printer = dict(printer_row)
        warnings: list[str] = []

        # The store/cashier copy is automatic and happens on every completed
        # transaction without asking the cashier first.
        try:
            cashier_receipt = giftcards.build_payment_receipt(
                db.get_setting("store_name", "POS OS"),
                sale_id,
                employee,
                created,
                lines,
                total,
                payment,
                printer["paper_width_mm"],
                "CASHIER COPY",
                cash,
                change,
                last4,
                remaining,
            )
            print_receipt(printer, cashier_receipt)
        except PrinterError as exc:
            warnings.append(f"Cashier copy did not print: {exc}")

        # This prompt occurs only after the database transaction has completed.
        customer_copy = messagebox.askyesno(
            "Customer receipt",
            "Print a receipt for the customer?",
        )
        if customer_copy:
            try:
                customer_receipt = giftcards.build_payment_receipt(
                    db.get_setting("store_name", "POS OS"),
                    sale_id,
                    employee,
                    created,
                    lines,
                    total,
                    payment,
                    printer["paper_width_mm"],
                    "CUSTOMER COPY",
                    cash,
                    change,
                    last4,
                    remaining,
                )
                print_receipt(printer, customer_receipt)
            except PrinterError as exc:
                warnings.append(f"Customer copy did not print: {exc}")

        return warnings

    giftcards._print_copies = print_after_sale

    original_payment = POSOS.cash_payment

    def wrapped_payment(self):
        existing = set(self.winfo_children())
        original_payment(self)

        # cash_payment builds the modal window and then returns. Find the newly
        # created payment window and remove the old pre-sale receipt checkbox.
        for window in set(self.winfo_children()) - existing:
            if not isinstance(window, tk.Toplevel):
                continue
            for widget in _walk_widgets(window):
                if isinstance(widget, tk.Checkbutton):
                    try:
                        if str(widget.cget("text")) == "Print customer receipt":
                            widget.pack_forget()
                    except tk.TclError:
                        pass

    POSOS.cash_payment = wrapped_payment
    POSOS._posos_post_transaction_receipts_patch = True


def _walk_widgets(parent):
    for child in parent.winfo_children():
        yield child
        yield from _walk_widgets(child)
