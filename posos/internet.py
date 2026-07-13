from __future__ import annotations

import os
import shutil
import subprocess
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk


class NetworkError(RuntimeError):
    pass


def _nmcli(*args: str, timeout: int = 25) -> str:
    nmcli = shutil.which("nmcli")
    if not nmcli:
        raise NetworkError("NetworkManager/nmcli is not installed on this POS OS system.")
    try:
        result = subprocess.run(
            [nmcli, "--colors", "no", *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NetworkError(str(exc)) from exc
    if result.returncode != 0:
        raise NetworkError((result.stderr or result.stdout or "Network command failed").strip())
    return result.stdout.strip()


def _split_escaped(line: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    escaped = False
    for char in line:
        if escaped:
            current.append(char)
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == ":":
            parts.append("".join(current))
            current = []
        else:
            current.append(char)
    parts.append("".join(current))
    return parts


def device_status() -> tuple[str, str]:
    ethernet = "Not connected"
    wifi = "Not connected"
    output = _nmcli("-t", "-f", "TYPE,STATE,CONNECTION", "device", "status")
    for line in output.splitlines():
        fields = _split_escaped(line)
        if len(fields) < 3:
            continue
        kind, state, connection = fields[0], fields[1], fields[2]
        text = connection if state == "connected" and connection else state.replace("-", " ").title()
        if kind == "ethernet":
            ethernet = text
        elif kind == "wifi":
            wifi = text
    return ethernet, wifi


def wifi_enabled() -> bool:
    return _nmcli("radio", "wifi").strip().lower() == "enabled"


def scan_wifi() -> list[dict[str, str]]:
    _nmcli("device", "wifi", "rescan", timeout=35)
    output = _nmcli("-t", "-f", "IN-USE,SSID,SIGNAL,SECURITY", "device", "wifi", "list", "--rescan", "yes", timeout=35)
    networks: list[dict[str, str]] = []
    seen: set[str] = set()
    for line in output.splitlines():
        fields = _split_escaped(line)
        if len(fields) < 4:
            continue
        active, ssid, signal, security = fields[:4]
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        networks.append({
            "active": "Yes" if active.strip() == "*" else "",
            "ssid": ssid,
            "signal": signal,
            "security": security or "Open",
        })
    networks.sort(key=lambda item: int(item["signal"] or 0), reverse=True)
    return networks


def connect_wifi(ssid: str, password: str | None = None) -> None:
    command = ["device", "wifi", "connect", ssid]
    if password:
        command += ["password", password]
    _nmcli(*command, timeout=60)


def disconnect_wifi() -> None:
    output = _nmcli("-t", "-f", "DEVICE,TYPE,STATE", "device", "status")
    for line in output.splitlines():
        fields = _split_escaped(line)
        if len(fields) >= 3 and fields[1] == "wifi" and fields[2] == "connected":
            _nmcli("device", "disconnect", fields[0])
            return


def _run_wifi_repair() -> str:
    python = Path("/opt/posos/current/venv/bin/python")
    if not python.exists():
        raise NetworkError("The POS OS repair environment was not found.")
    try:
        result = subprocess.run(
            ["sudo", "-n", str(python), "-m", "posos.repair"],
            check=False,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NetworkError(f"Could not start Wi-Fi repair: {exc}") from exc
    if result.returncode != 0:
        details = (result.stderr or result.stdout or "Wi-Fi repair failed").strip()
        raise NetworkError(details)
    return result.stdout.strip()


def _write_diagnostic_report() -> Path:
    data_dir = Path(os.environ.get("POSOS_DATA_DIR", "/var/lib/posos"))
    data_dir.mkdir(parents=True, exist_ok=True)
    report = data_dir / "network-diagnostic.txt"
    commands = [
        ["nmcli", "device", "status"],
        ["nmcli", "radio", "all"],
        ["ip", "link"],
        ["ip", "route"],
        ["lspci", "-k"],
        ["sudo", "-n", "rfkill", "list"],
    ]
    lines = [f"POS OS network diagnostic - {datetime.now().isoformat(timespec='seconds')}", ""]
    for command in commands:
        lines.append(f"$ {' '.join(command)}")
        try:
            completed = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
            lines.append((completed.stdout or completed.stderr or "(no output)").strip())
        except Exception as exc:
            lines.append(f"ERROR: {exc}")
        lines.append("")
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def build_internet_tab(root, parent) -> None:
    status_box = ttk.LabelFrame(parent, text="Connection status", padding=12)
    status_box.pack(fill="x", pady=(0, 10))
    ethernet_var = tk.StringVar(value="Checking…")
    wifi_var = tk.StringVar(value="Checking…")
    radio_var = tk.StringVar(value="Checking…")
    ttk.Label(status_box, text="Ethernet:", font=("DejaVu Sans", 13, "bold")).grid(row=0, column=0, sticky="w", padx=5, pady=4)
    ttk.Label(status_box, textvariable=ethernet_var).grid(row=0, column=1, sticky="w", padx=5, pady=4)
    ttk.Label(status_box, text="Wi-Fi:", font=("DejaVu Sans", 13, "bold")).grid(row=1, column=0, sticky="w", padx=5, pady=4)
    ttk.Label(status_box, textvariable=wifi_var).grid(row=1, column=1, sticky="w", padx=5, pady=4)
    ttk.Label(status_box, text="Wi-Fi radio:", font=("DejaVu Sans", 13, "bold")).grid(row=2, column=0, sticky="w", padx=5, pady=4)
    ttk.Label(status_box, textvariable=radio_var).grid(row=2, column=1, sticky="w", padx=5, pady=4)

    tree = ttk.Treeview(parent, columns=("signal", "security", "connected"), show="tree headings", height=10)
    tree.heading("#0", text="Wi-Fi network")
    tree.heading("signal", text="Signal")
    tree.heading("security", text="Security")
    tree.heading("connected", text="Connected")
    tree.column("#0", width=360)
    tree.column("signal", width=100, anchor="center")
    tree.column("security", width=180, anchor="center")
    tree.column("connected", width=100, anchor="center")
    tree.pack(fill="both", expand=True)

    def refresh():
        try:
            ethernet, wifi = device_status()
            enabled = wifi_enabled()
            ethernet_var.set(ethernet)
            wifi_var.set(wifi)
            radio_var.set("On" if enabled else "Off")
            tree.delete(*tree.get_children())
            if enabled and wifi.lower() != "unavailable":
                for index, network in enumerate(scan_wifi()):
                    tree.insert("", "end", iid=str(index), text=network["ssid"], values=(f"{network['signal']}%", network["security"], network["active"]))
        except NetworkError as exc:
            messagebox.showerror("Internet", str(exc))

    def selected_ssid() -> str | None:
        selection = tree.selection()
        if not selection:
            messagebox.showinfo("Internet", "Select a Wi-Fi network first.")
            return None
        return str(tree.item(selection[0], "text"))

    def connect_selected():
        ssid = selected_ssid()
        if not ssid:
            return
        security = str(tree.set(tree.selection()[0], "security"))
        password = None
        if security and security.lower() != "open":
            password = root.ask_text("Wi-Fi password", f"Password for {ssid}", "", True)
            if password is None:
                return
        try:
            connect_wifi(ssid, password)
            refresh()
            messagebox.showinfo("Internet", f"Connected to {ssid}.")
        except NetworkError as exc:
            messagebox.showerror("Wi-Fi connection failed", str(exc))

    def set_wifi(enabled: bool):
        try:
            _nmcli("radio", "wifi", "on" if enabled else "off")
            refresh()
        except NetworkError as exc:
            messagebox.showerror("Internet", str(exc))

    def disconnect():
        try:
            disconnect_wifi()
            refresh()
        except NetworkError as exc:
            messagebox.showerror("Internet", str(exc))

    def repair_wifi():
        if not messagebox.askyesno(
            "Repair Wi-Fi",
            "Repair Debian package sources and install the required Wi-Fi software?\n\n"
            "Keep USB tethering connected if Wi-Fi packages must be downloaded.",
        ):
            return
        try:
            messagebox.showinfo("Repair Wi-Fi", "Repair is starting. This can take several minutes.")
            result = _run_wifi_repair()
            refresh()
            messagebox.showinfo("Repair Wi-Fi", result or "Wi-Fi repair completed. Reboot if Wi-Fi is still unavailable.")
        except NetworkError as exc:
            messagebox.showerror("Wi-Fi repair failed", str(exc))

    def save_report():
        try:
            report = _write_diagnostic_report()
            messagebox.showinfo("Network diagnostic", f"Diagnostic report saved to:\n{report}")
        except Exception as exc:
            messagebox.showerror("Network diagnostic", str(exc))

    controls = ttk.Frame(parent)
    controls.pack(fill="x", pady=(10, 0))
    for text, command in [
        ("Refresh", refresh),
        ("Connect selected", connect_selected),
        ("Disconnect", disconnect),
        ("Wi-Fi On", lambda: set_wifi(True)),
        ("Wi-Fi Off", lambda: set_wifi(False)),
        ("Repair Wi-Fi", repair_wifi),
        ("Save Diagnostic", save_report),
    ]:
        ttk.Button(controls, text=text, command=command).pack(side="left", fill="x", expand=True, padx=2, ipady=8)

    ttk.Label(parent, text="USB tethering appears as Ethernet. Repair Wi-Fi can install missing Debian Wi-Fi packages automatically.", wraplength=850).pack(anchor="w", pady=(10, 0))
    root.after(100, refresh)
