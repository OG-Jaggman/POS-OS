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


def build_receipt_text(
    store_name: str,
    sale_id: int,
    employee_name: str,
    created_at: str,
    lines: list[dict],
    total_cents: int,
    cash_cents: int,
    change_cents: int,
    paper_width_mm: int,
) -> str:
    layout = ReceiptLayout(paper_width_mm)
    out = [
        layout.center(store_name or "POS OS"),
        layout.rule(),
        layout.line(f"Sale #{sale_id}", created_at),
        layout.line("Employee", employee_name),
        layout.rule(),
    ]
    for item in lines:
        qty = int(item["qty"])
        name = str(item["name"])
        unit = int(item["price_cents"])
        out.append(name[: layout.chars_per_line])
        out.append(layout.line(f"  {qty} x ${unit / 100:.2f}", f"${qty * unit / 100:.2f}"))
    out += [
        layout.rule(),
        layout.line("TOTAL", f"${total_cents / 100:.2f}"),
        layout.line("Cash", f"${cash_cents / 100:.2f}"),
        layout.line("Change", f"${change_cents / 100:.2f}"),
        layout.rule(),
        layout.center("Thank you!"),
        "",
        "",
        "",
    ]
    return "\n".join(out)


def _escpos_bytes(text: str, cut: bool = True) -> bytes:
    data = b"\x1b@" + text.encode("cp437", errors="replace")
    data += b"\n\n\n"
    if cut:
        data += b"\x1dV\x00"
    return data


def _drawer_bytes(printer: dict) -> bytes:
    pin = 1 if int(printer.get("drawer_pin", 0)) == 1 else 0
    on_ms = max(2, min(510, int(printer.get("drawer_on_ms", 120))))
    off_ms = max(2, min(510, int(printer.get("drawer_off_ms", 240))))
    # ESC/POS stores pulse lengths in 2 ms units.
    return bytes((0x1B, 0x70, pin, on_ms // 2, off_ms // 2))


def _network_send(printer: dict, payload: bytes) -> None:
    host = (printer.get("host") or "").strip()
    port = int(printer.get("port") or 9100)
    if not host:
        raise PrinterError("Network printer IP/hostname is empty")
    try:
        with socket.create_connection((host, port), timeout=8) as sock:
            sock.sendall(payload)
    except OSError as exc:
        raise PrinterError(f"Could not reach {host}:{port}: {exc}") from exc


def _system_raw(printer: dict, payload: bytes) -> None:
    queue = (printer.get("queue_name") or "").strip()
    lp = shutil.which("lp")
    if not lp:
        raise PrinterError("The 'lp' command is not installed")
    command = [lp, "-o", "raw"]
    if queue:
        command += ["-d", queue]
    try:
        subprocess.run(command, input=payload, check=True, timeout=20)
    except (subprocess.SubprocessError, OSError) as exc:
        raise PrinterError(f"System printer failed: {exc}") from exc


def _windows_raw(printer: dict, payload: bytes, job_name: str) -> None:
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


def print_receipt(printer: dict, receipt_text: str) -> None:
    printer_type = printer.get("printer_type", "network")
    payload = _escpos_bytes(receipt_text, cut=bool(printer.get("auto_cut", 1)))

    if printer_type == "network":
        _network_send(printer, payload)
        return
    if printer_type in {"system", "cups"}:
        _system_raw(printer, payload)
        return
    if printer_type == "windows":
        _windows_raw(printer, payload, "POS OS Receipt")
        return
    if printer_type == "file":
        target = Path(printer.get("file_path") or Path.home() / "posos-receipt.txt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(receipt_text, encoding="utf-8")
        return
    raise PrinterError(f"Unsupported printer type: {printer_type}")


def open_cash_drawer(printer: dict, force: bool = False) -> None:
    if not force and not bool(printer.get("drawer_enabled", 0)):
        return

    printer_type = printer.get("printer_type", "network")
    payload = _drawer_bytes(printer)

    if printer_type == "network":
        _network_send(printer, payload)
        return
    if printer_type in {"system", "cups"}:
        _system_raw(printer, payload)
        return
    if printer_type == "windows":
        _windows_raw(printer, payload, "POS OS Open Drawer")
        return
    if printer_type == "file":
        raise PrinterError("A file printer cannot open a physical cash drawer")
    raise PrinterError(f"Unsupported printer type: {printer_type}")
