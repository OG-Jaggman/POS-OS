from __future__ import annotations

import shutil
import socket
import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from .app import DB, POSOS


POS_IP = "192.168.50.1/24"
DEFAULT_PRINTER_IP = "192.168.50.2"
PRINTER_PORT = 9100
CONNECTION_NAME = "POS OS Direct Printer"


def _run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _ethernet_interfaces() -> list[str]:
    if not shutil.which("nmcli"):
        return []
    try:
        result = _run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"])
    except (OSError, subprocess.SubprocessError):
        return []

    interfaces: list[str] = []
    for line in result.stdout.splitlines():
        if not line or ":" not in line:
            continue
        device, device_type = line.split(":", 1)
        if device and device_type == "ethernet" and device != "lo":
            interfaces.append(device)
    return interfaces


def _configure_interface(interface: str) -> None:
    if not shutil.which("nmcli"):
        raise RuntimeError("NetworkManager's nmcli command is not installed.")

    existing = subprocess.run(
        ["nmcli", "-t", "-f", "NAME", "connection", "show"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.splitlines()

    common = [
        "ipv4.method", "manual",
        "ipv4.addresses", POS_IP,
        "ipv4.gateway", "",
        "ipv4.dns", "",
        "ipv4.never-default", "yes",
        "ipv6.method", "disabled",
        "connection.autoconnect", "yes",
        "connection.interface-name", interface,
    ]

    if CONNECTION_NAME in existing:
        _run(["nmcli", "connection", "modify", CONNECTION_NAME, *common])
    else:
        _run([
            "nmcli", "connection", "add",
            "type", "ethernet",
            "ifname", interface,
            "con-name", CONNECTION_NAME,
            *common,
        ])

    _run(["nmcli", "connection", "up", CONNECTION_NAME], timeout=30)


def _port_open(host: str, port: int = PRINTER_PORT, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _find_printer(preferred: str) -> str | None:
    candidates = [preferred]
    candidates.extend(f"192.168.50.{number}" for number in range(2, 21) if f"192.168.50.{number}" != preferred)
    for host in candidates:
        if _port_open(host):
            return host
    return None


def _save_network_printer(host: str) -> None:
    current = DB.default_printer()
    if current and current["printer_type"] == "network":
        printer_id = current["id"]
        name = current["name"] or "Direct Ethernet Receipt Printer"
        paper = current["paper_width_mm"]
        auto_cut = bool(current["auto_cut"])
        drawer_enabled = bool(current["drawer_enabled"])
        drawer_pin = current["drawer_pin"]
        drawer_on = current["drawer_on_ms"]
        drawer_off = current["drawer_off_ms"]
    else:
        printer_id = None
        name = "Direct Ethernet Receipt Printer"
        paper = 80
        auto_cut = True
        drawer_enabled = True
        drawer_pin = 0
        drawer_on = 120
        drawer_off = 240

    DB.save_printer(
        printer_id,
        name,
        "network",
        host,
        PRINTER_PORT,
        "",
        "",
        paper,
        auto_cut,
        drawer_enabled,
        drawer_pin,
        drawer_on,
        drawer_off,
        True,
        True,
    )


def _open_direct_setup(self: POSOS) -> None:
    interfaces = _ethernet_interfaces()
    if not interfaces:
        messagebox.showerror(
            "Direct Ethernet Printer",
            "POS OS could not find an Ethernet port. Make sure the Ethernet adapter is enabled.",
            parent=self,
        )
        return

    window = tk.Toplevel(self)
    window.title("Direct Ethernet Printer Setup")
    window.transient(self)
    window.grab_set()
    window.attributes("-topmost", True)
    window.geometry("760x560")

    frame = ttk.Frame(window, padding=22)
    frame.pack(fill="both", expand=True)
    ttk.Label(frame, text="Direct Ethernet Printer", font=("DejaVu Sans", 22, "bold")).pack(anchor="w")
    ttk.Label(
        frame,
        text=(
            "Connect the receipt printer directly to this register's Ethernet port. "
            "Wi-Fi can stay connected for internet access while Ethernet is used only for the printer."
        ),
        wraplength=700,
        justify="left",
    ).pack(anchor="w", pady=(8, 18))

    interface_var = tk.StringVar(value=interfaces[0])
    printer_ip_var = tk.StringVar(value=DEFAULT_PRINTER_IP)

    form = ttk.Frame(frame)
    form.pack(fill="x")
    ttk.Label(form, text="Register Ethernet port").grid(row=0, column=0, sticky="w", pady=7)
    ttk.Combobox(form, textvariable=interface_var, values=interfaces, state="readonly").grid(row=0, column=1, sticky="ew", padx=8, pady=7)
    ttk.Label(form, text="Printer IP address").grid(row=1, column=0, sticky="w", pady=7)
    ttk.Entry(form, textvariable=printer_ip_var).grid(row=1, column=1, sticky="ew", padx=8, pady=7, ipady=5)
    ttk.Button(
        form,
        text="⌨",
        command=lambda: self._edit_var(printer_ip_var),
    ).grid(row=1, column=2, pady=7)
    form.columnconfigure(1, weight=1)

    info = ttk.Label(
        frame,
        text=(
            "POS OS will set this port to 192.168.50.1. Set the printer to 192.168.50.2, "
            "subnet mask 255.255.255.0, with no gateway. Most receipt printers use port 9100."
        ),
        wraplength=700,
        justify="left",
    )
    info.pack(anchor="w", pady=16)

    status_var = tk.StringVar(value="Ready. Plug in the Ethernet cable, then press Set Up & Test.")
    ttk.Label(frame, textvariable=status_var, wraplength=700, font=("DejaVu Sans", 13, "bold")).pack(fill="x", pady=12)

    controls = ttk.Frame(frame)
    controls.pack(side="bottom", fill="x")
    close_button = ttk.Button(controls, text="Close", command=window.destroy)
    close_button.pack(side="left", fill="x", expand=True, padx=(0, 5), ipady=11)
    setup_button = ttk.Button(controls, text="Set Up & Test")
    setup_button.pack(side="left", fill="x", expand=True, padx=(5, 0), ipady=11)

    def finish_success(host: str) -> None:
        _save_network_printer(host)
        status_var.set(f"Connected! Printer saved at {host}:{PRINTER_PORT}.")
        setup_button.configure(state="normal")
        close_button.configure(state="normal")
        messagebox.showinfo(
            "Direct Ethernet Printer",
            f"The Ethernet port is configured and the printer answered at {host}:{PRINTER_PORT}.\n\n"
            "It is now the default receipt printer.",
            parent=window,
        )

    def finish_failure(message: str) -> None:
        status_var.set(message)
        setup_button.configure(state="normal")
        close_button.configure(state="normal")
        messagebox.showerror("Direct Ethernet Printer", message, parent=window)

    def worker() -> None:
        try:
            interface = interface_var.get().strip()
            preferred = printer_ip_var.get().strip() or DEFAULT_PRINTER_IP
            socket.inet_aton(preferred)
            _configure_interface(interface)
            host = _find_printer(preferred)
            if not host:
                raise RuntimeError(
                    "The register Ethernet port was configured, but no printer answered on port 9100. "
                    "Check the cable and set the printer IP to 192.168.50.2 with subnet mask 255.255.255.0."
                )
            window.after(0, lambda: finish_success(host))
        except (OSError, subprocess.SubprocessError, RuntimeError) as exc:
            window.after(0, lambda: finish_failure(str(exc)))

    def start() -> None:
        setup_button.configure(state="disabled")
        close_button.configure(state="disabled")
        status_var.set("Configuring the Ethernet port and searching for the printer…")
        threading.Thread(target=worker, daemon=True).start()

    setup_button.configure(command=start)


def patch_direct_ethernet_printer() -> None:
    original = POSOS.build_printers_tab
    if getattr(original, "_posos_direct_ethernet", False):
        return

    def wrapped(self: POSOS, parent) -> None:
        original(self, parent)
        button = ttk.Button(
            parent,
            text="Direct Ethernet Printer Setup",
            command=lambda: _open_direct_setup(self),
        )
        button.pack(fill="x", pady=(10, 0), ipady=10)

    wrapped._posos_direct_ethernet = True
    POSOS.build_printers_tab = wrapped
