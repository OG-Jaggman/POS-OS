from __future__ import annotations

from tkinter import messagebox


def patch_receipt_prompt_flow() -> None:
    """Always print cashier copy, then ask about the customer copy after sale."""
    from . import giftcards

    if getattr(giftcards, "_posos_receipt_prompt_patch", False):
        return

    def print_copies(
        db,
        sale_id,
        employee,
        created,
        lines,
        total,
        payment,
        _customer_copy_ignored,
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

        def print_one(copy_name: str) -> None:
            try:
                receipt = giftcards.build_payment_receipt(
                    db.get_setting("store_name", "POS OS"),
                    sale_id,
                    employee,
                    created,
                    lines,
                    total,
                    payment,
                    printer["paper_width_mm"],
                    copy_name,
                    cash,
                    change,
                    last4,
                    remaining,
                )
                giftcards.print_receipt(printer, receipt)
            except giftcards.PrinterError as exc:
                warnings.append(f"{copy_name.title()} did not print: {exc}")

        # The cashier copy is automatic and happens first, immediately after
        # the transaction has successfully committed.
        print_one("CASHIER COPY")

        if messagebox.askyesno(
            "Customer receipt",
            "Transaction complete. Print a customer receipt?",
        ):
            print_one("CUSTOMER COPY")

        return warnings

    giftcards._print_copies = print_copies
    giftcards._posos_receipt_prompt_patch = True
