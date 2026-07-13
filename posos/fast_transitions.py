from __future__ import annotations

import tkinter as tk


def patch_fast_screen_transitions() -> None:
    """Display a loading screen before constructing widget-heavy POS pages."""
    from .app import POSOS

    if getattr(POSOS, "_posos_fast_transitions_patch", False):
        return

    real_register = POSOS.register_screen
    real_manager = POSOS.manager_screen

    def show_loading(self, title: str) -> None:
        self.clear()
        self.configure(bg="#f4f3ef")
        shell = tk.Frame(self, bg="#f4f3ef")
        shell.pack(fill="both", expand=True)
        tk.Label(
            shell,
            text=title,
            bg="#f4f3ef",
            fg="#242424",
            font=("DejaVu Sans", 24, "bold"),
        ).place(relx=0.5, rely=0.46, anchor="center")
        tk.Label(
            shell,
            text="Loading…",
            bg="#f4f3ef",
            fg="#777777",
            font=("DejaVu Sans", 15),
        ).place(relx=0.5, rely=0.54, anchor="center")
        self.update_idletasks()

    def register_screen(self):
        show_loading(self, "Opening Register")
        self.after(15, lambda: real_register(self))

    def manager_screen(self):
        if not self.current_user or self.current_user["role"] != "manager":
            return
        show_loading(self, "Opening Manager Settings")
        self.after(15, lambda: real_manager(self))

    POSOS.register_screen = register_screen
    POSOS.manager_screen = manager_screen
    POSOS._posos_fast_transitions_patch = True
