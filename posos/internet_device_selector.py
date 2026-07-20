from __future__ import annotations

import subprocess
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from . import internet


PRINTER_CONNECTION = "POS OS Direct Printer"


def _devices() -> list[dict[str, str]]:
    output = internet._nmcli(
        "-t",
        "-f",
        "DEVICE,TYPE,STATE,CONNECTION",
        "device",
        "status",
    )
    devices: list[dict[str, str]] = []
    for line in output.splitlines():
        fields = internet._split_escaped(line)
        if len(fields) < 4:
            continue
        device, kind, state, connection = fields[:4]
        if not device or device == "lo" or kind not in {"ethernet", "wifi", "gsm", "cdma"}:
            continue
        devices.append(
            {
                "device": device,
                "type": kind,
                "state": state,
                "connection": connection,
            }
        )
    return devices


def _default_device() -> str:
    try:
        output = subprocess.run(
            ["ip", "route", "show", "default"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    for line in output.splitlines():
        fields = line.split()
        if "dev" in fields:
            index = fields.index("dev")
            if index + 1 < len(fields):
                return fields[index + 1]
    return ""


def _connection_for_device(device: str) -> str:
    output = internet._nmcli("-t", "-f", "GENERAL.CONNECTION", "device", "show", device)
    for line in output.splitlines():
        fields = internet._split_escaped(line)
        if len(fields) >= 2 and fields[0] == "GENERAL.CONNECTION":
            return fields[1]
    return ""


def _activate_device(device: str) -> str:
    internet._nmcli("device", "connect", device, timeout=60)
    connection = _connection_for_device(device)
    if not connection or connection == "--":
        raise internet.NetworkError(f"{device} connected, but NetworkManager did not report a connection profile.")
    return connection


def _set_preferred_internet_device(device: str) -> str:
    connection = _connection_for_device(device)
    if not connection or connection == "--":
        connection = _activate_device(device)

    if connection == PRINTER_CONNECTION:
        raise internet.NetworkError(
            "That Ethernet port is reserved for the direct receipt printer. Select USB tethering, Wi-Fi, or another Ethernet adapter for Internet."
        )

    # Give the chosen input the best route metric. Other active Internet links
    # remain usable as fallbacks, while the dedicated printer profile is never
    # allowed to become the system's default Internet route.
    internet._nmcli(
        "connection",
        "modify",
        connection,
        "ipv4.never-default",
        "no",
        "ipv4.route-metric",
        "10",
        "ipv6.never-default",
        "no",
        "ipv6.route-metric",
        "10",
    )

    for item in _devices():
        other = item["connection"]
        if not other or other == "--" or other == connection:
            continue
        if other == PRINTER_CONNECTION:
            try:
                internet._nmcli(
                    "connection",
                    "modify",
                    other,
                    "ipv4.never-default",
                    "yes",
                    "ipv6.never-default",
                    "yes",
                )
            except internet.NetworkError:
                pass
            continue
        try:
            internet._nmcli(
                "connection",
                "modify",
                other,
                "ipv4.route-metric",
                "600",
                "ipv6.route-metric",
                "600",
            )
        except internet.NetworkError:
            pass

    internet._nmcli("connection", "up", connection, "ifname", device, timeout=60)
    return connection


def _disconnect_device(device: str) -> None:
    connection = _connection_for_device(device)
    if connection == PRINTER_CONNECTION:
        raise internet.NetworkError(
            "That port is currently used by the direct receipt printer. Disconnect it from Printers & Drawer instead."
        )
    internet._nmcli("device", "disconnect", device)


def _add_device_selector(root, parent) -> None:
    first_child = parent.winfo_children()[0] if parent.winfo_children() else None
    box = ttk.LabelFrame(parent, text="Internet input device", padding=12)
    pack_options = {"fill": "x", "pady": (0, 10)}
    if first_child is not None:
        pack_options["before"] = first_child
    box.pack(**pack_options)

    ttk.Label(
        box,
        text=(
            "Choose which adapter POS OS should use for Internet. USB tethering normally appears as Ethernet. "
            "The direct-printer Ethernet port stays isolated from Internet traffic."
        ),
        wraplength=840,
        justify="left",
    ).pack(anchor="w", pady=(0, 8))

    selected = tk.StringVar()
    status = tk.StringVar(value="Checking network devices…")
    choices: dict[str, dict[str, str]] = {}

    row = ttk.Frame(box)
    row.pack(fill="x")
    selector = ttk.Combobox(row, textvariable=selected, state="readonly")
    selector.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=5)

    def refresh_devices(show_error: bool = True) -> None:
        try:
            default = _default_device()
            items = _devices()
            choices.clear()
            labels: list[str] = []
            selected_label = ""
            for item in items:
                device = item["device"]
                connection = item["connection"] or "No profile"
                kind = "USB/Ethernet" if item["type"] == "ethernet" else item["type"].upper()
                flags: list[str] = []
                if device == default:
                    flags.append("CURRENT INTERNET")
                if connection == PRINTER_CONNECTION:
                    flags.append("PRINTER ONLY")
                suffix = f" — {', '.join(flags)}" if flags else ""
                label = f"{device} | {kind} | {connection} | {item['state']}{suffix}"
                choices[label] = item
                labels.append(label)
                if device == default:
                    selected_label = label
            selector.configure(values=labels)
            if selected.get() not in choices:
                selected.set(selected_label or (labels[0] if labels else ""))
            status.set(
                f"Current Internet input: {default}" if default else "No default Internet route detected."
            )
        except internet.NetworkError as exc:
            status.set(str(exc))
            if show_error:
                messagebox.showerror("Internet devices", str(exc), parent=root)

    def chosen_device() -> str | None:
        item = choices.get(selected.get())
        if not item:
            messagebox.showinfo("Internet devices", "Select a network device first.", parent=root)
            return None
        return item["device"]

    def run_action(action, progress: str, success) -> None:
        device = chosen_device()
        if not device:
            return
        status.set(progress)
        for button in action_buttons:
            button.configure(state="disabled")

        def worker() -> None:
            try:
                result = action(device)
                root.after(0, lambda: finish_success(result, success))
            except (internet.NetworkError, OSError, subprocess.SubprocessError) as exc:
                root.after(0, lambda: finish_error(str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def finish_success(result, success) -> None:
        refresh_devices(False)
        for button in action_buttons:
            button.configure(state="normal")
        messagebox.showinfo("Internet devices", success(result), parent=root)

    def finish_error(message: str) -> None:
        status.set(message)
        for button in action_buttons:
            button.configure(state="normal")
        messagebox.showerror("Internet devices", message, parent=root)

    refresh_button = ttk.Button(row, text="Refresh devices", command=refresh_devices)
    refresh_button.pack(side="left", ipadx=8, ipady=5)

    buttons = ttk.Frame(box)
    buttons.pack(fill="x", pady=(8, 0))
    action_buttons: list[ttk.Button] = []

    preferred_button = ttk.Button(
        buttons,
        text="Use selected for Internet",
        command=lambda: run_action(
            _set_preferred_internet_device,
            "Switching the preferred Internet input…",
            lambda connection: f"Internet now prefers {connection}. Other connections remain available as backup.",
        ),
    )
    preferred_button.pack(side="left", fill="x", expand=True, padx=(0, 3), ipady=8)
    action_buttons.append(preferred_button)

    connect_button = ttk.Button(
        buttons,
        text="Connect selected",
        command=lambda: run_action(
            _activate_device,
            "Connecting the selected device…",
            lambda connection: f"Connected using {connection}.",
        ),
    )
    connect_button.pack(side="left", fill="x", expand=True, padx=3, ipady=8)
    action_buttons.append(connect_button)

    disconnect_button = ttk.Button(
        buttons,
        text="Disconnect selected",
        command=lambda: run_action(
            lambda device: (_disconnect_device(device), device)[1],
            "Disconnecting the selected device…",
            lambda device: f"Disconnected {device}.",
        ),
    )
    disconnect_button.pack(side="left", fill="x", expand=True, padx=(3, 0), ipady=8)
    action_buttons.append(disconnect_button)

    ttk.Label(box, textvariable=status, font=("DejaVu Sans", 12, "bold")).pack(anchor="w", pady=(8, 0))
    root.after(100, refresh_devices)


def patch_internet_device_selector() -> None:
    original = internet.build_internet_tab
    if getattr(original, "_posos_device_selector", False):
        return

    def wrapped(root, parent) -> None:
        original(root, parent)
        _add_device_selector(root, parent)

    wrapped._posos_device_selector = True
    internet.build_internet_tab = wrapped
