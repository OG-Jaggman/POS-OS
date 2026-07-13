from __future__ import annotations

import platform
import shutil
import socket
import subprocess
from dataclasses import dataclass
from pathlib import Path


class PrinterError(RuntimeError):
    pass


@dataclass
class ReceiptLayout:
    paper_width_mm: int = 80

    @property
    def chars_per_line(self) -> int:
        return 48 if self.paper_width_mm == 80 else 32

    def line(self, left: str = "", right: str = "") -> str:
        width = self.chars_per_line
        left = str(left)
        right = str(right)
        if not right:
            return left[:width]
        gap = max(1, width - len(left) - len(right))
        return (left[: max(0, width - len(right) - 1)] + " " * gap + right)[:width]

    def center(self, text: str) -> str:
        return str(text)[: self.chars_per_line].center(self.chars_per_line)

    def rule(self, char: str = "-") -> str:
        return char * self.chars_per_line


def build_receipt_text(store_name: str, sale_id: int, employee_name: str, created_at: str,
                       lines: list[dict], total_cents: int, cash_cents: int,
                       change_cents: int, paper_width_mm: int) -> str:
    layout = ReceiptLayout(paper_width_mm)
    out = [layout.center(store_name or "POS OS"), layout.rule(),
           layout.line(f"Sale #{sale_id}", created_at),
           layout.line("Employee", employee_name), layout.rule()]
    for item in lines:
        qty = int(item["qty"])
        name = str(item["name"])
        unit = int(item["price_cents"])
        out.append(name[: layout.chars_per_line])
        out.append(layout.line(f"  {qty} x ${unit / 100:.2f}", f"${qty * unit / 100:.2f}"))
    out += [layout.rule(), layout.line("TOTAL", f"${total_cents / 100:.2f}"),
            layout.line("Cash", f"${cash_cents / 100:.2f}"),
            layout.line("Change", f"${change_cents / 100:.2f}"),
            layout.rule(), layout.center("Thank you!"), "", "", ""]
    return "\n".join(out)


def _escpos_bytes(text: str, cut: bool = True) -> bytes:
    data = b"\x1b@" + text.encode("cp437", errors="replace")
    data += b"\n\n\n"
    if cut:
        data += b"\x1dV\x00"
    return data


def _drawer_bytes(printer: dict) -> bytes:
    # ESC p m t1 t2. Most printers use m=0 for drawer pin 2 and m=1 for pin 5.
    pin = int(printer.get("drawer_pin") or 2)
    connector = 1 if pin == 5 else 0
    on_ms = max(2, min(510, int(printer.get("drawer_on_ms") or 120)))
    off_ms = max(2, min(510, int(printer.get("drawer_off_ms") or 240)))
    return bytes((0x1B, 0x70, connector, min(255, on_ms // 2), min(255, off_ms // 2)))


def _send_raw(printer: dict, payload: bytes, job_name: str) -> None:
    ptype = printer.get("printer_type", "network")

    if ptype == "network":
        host = (printer.get("host") or "").strip()
        port = int(printer.get("port") or 9100)
        if not host:
            raise PrinterError("Network printer IP/hostname is empty")
        try:
            with socket.create_connection((host, port), timeout=8) as sock:
                sock.sendall(payload)
        except OSError as exc:
            raise PrinterError(f"Could not reach {host}:{port}: {exc}") from exc
        return

    if ptype in {"system", "cups"}:
        queue = (printer.get("queue_name") or "").strip()
        lp = shutil.which("lp")
        if not lp:
            raise PrinterError("The 'lp' command is not installed")
        cmd = [lp, "-o", "raw", "-t", job_name]
        if queue:
            cmd += ["-d", queue]
        try:
            subprocess.run(cmd, input=payload, check=True, timeout=20)
        except (subprocess.SubprocessError, OSError) as exc:
            raise PrinterError(f"System printer failed: {exc}") from exc
        return

    if ptype == "windows":
        if platform.system() != "Windows":
            raise PrinterError("Windows printer mode only works when POS OS is running on Windows")
        queue = (printer.get("queue_name") or "").strip()
        try:
            import win32print  # type: ignore
            handle = win32print.OpenPrinter(queue or win32print.GetDefaultPrinter())
            try:
                win32print.StartDocPrinter(handle, 1, (job_name, None, "RAW"))
                win32print.StartPagePrinter(handle)
                win32print.WritePrinter(handle, payload)
                win32print.EndPagePrinter(handle)
                win32print.EndDocPrinter(handle)
            finally:
                win32print.ClosePrinter(handle)
        except ImportError as exc:
            raise PrinterError("Install pywin32 to use Windows printers") from exc
        except Exception as exc:
            raise PrinterError(f"Windows printer failed: {exc}") from exc
        return

    if ptype == "file":
        target = Path(printer.get("file_path") or Path.home() / "posos-receipt.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        if job_name == "POS OS Cash Drawer":
            with target.open("a", encoding="utf-8") as handle:
                handle.write("\n[CASH DRAWER OPEN PULSE]\n")
        else:
            target.write_bytes(payload)
        return

    raise PrinterError(f"Unsupported printer type: {ptype}")


def print_receipt(printer: dict, receipt_text: str) -> None:
    _send_raw(
        printer,
        _escpos_bytes(receipt_text, cut=bool(printer.get("auto_cut", 1))),
        "POS OS Receipt",
    )


def open_cash_drawer(printer: dict, force: bool = False) -> bool:
    if not force and not bool(printer.get("drawer_enabled", 0)):
        return False
    _send_raw(printer, _drawer_bytes(printer), "POS OS Cash Drawer")
    return True
