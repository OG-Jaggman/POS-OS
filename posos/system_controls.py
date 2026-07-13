from __future__ import annotations

from tkinter import messagebox, ttk


def patch_system_controls() -> None:
    from .app import POSOS
    from .updater import UpdateError, _reboot_system

    if getattr(POSOS, "_posos_system_controls_patch", False):
        return
    original = POSOS.build_system_tab

    def wrapped(self, parent):
        original(self, parent)

        def reboot_system():
            if not messagebox.askyesno(
                "Reboot POS OS",
                "Reboot the entire Linux system now?",
            ):
                return
            try:
                # Use the same tested fallback chain as the post-update reboot:
                # systemctl, loginctl, then passwordless sudo systemctl.
                _reboot_system()
            except UpdateError as exc:
                messagebox.showerror("Reboot failed", str(exc))

        ttk.Separator(parent).pack(fill="x", pady=12)
        ttk.Button(
            parent,
            text="REBOOT POS OS",
            command=reboot_system,
        ).pack(fill="x", pady=5, ipady=12)

    POSOS.build_system_tab = wrapped
    POSOS._posos_system_controls_patch = True
