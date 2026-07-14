from __future__ import annotations

import tkinter as tk
from tkinter import ttk


BG = "#f4f3ef"
PANEL = "#ffffff"
ACCENT = "#ffa000"
TEXT = "#242424"
MUTED = "#777777"
BORDER = "#dedbd5"


def patch_fast_manager() -> None:
    from .app import POSOS

    if getattr(POSOS, "_posos_fast_manager_patch", False):
        return

    def manager_screen(self):
        if self.current_user["role"] != "manager":
            return

        existing = getattr(self, "_manager_window", None)
        if existing is not None and existing.winfo_exists():
            existing.lift()
            existing.focus_force()
            return

        window = tk.Toplevel(self)
        self._manager_window = window
        window.title("Manager Center")
        window.configure(bg=BG)
        window.transient(self)
        window.grab_set()
        try:
            window.attributes("-fullscreen", True)
        except tk.TclError:
            window.geometry("1024x700")

        def close_manager():
            try:
                window.grab_release()
            except tk.TclError:
                pass
            self._manager_window = None
            window.destroy()

        window.protocol("WM_DELETE_WINDOW", close_manager)

        header = tk.Frame(window, bg=PANEL, height=64, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Manager Center", bg=PANEL, fg=TEXT, font=("DejaVu Sans", 24, "bold")).pack(side="left", padx=20)
        tk.Label(header, text=f"Signed in as {self.current_user['name']}", bg=PANEL, fg=MUTED, font=("DejaVu Sans", 10)).pack(side="left", padx=8)
        tk.Button(header, text="Back to Register", command=close_manager, bg=ACCENT, fg=TEXT, activebackground="#e58b00", relief="flat", font=("DejaVu Sans", 11, "bold"), padx=16, pady=9).pack(side="right", padx=16)

        body = tk.Frame(window, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        notebook = ttk.Notebook(body, style="Modern.TNotebook")
        notebook.pack(fill="both", expand=True)

        builders = {
            "Items": self.build_items_tab,
            "Employees": self.build_employees_tab,
            "Sales": self.build_sales_tab,
            "Printers & Drawer": self.build_printers_tab,
            "System": self.build_system_tab,
        }
        tabs: dict[str, ttk.Frame] = {}
        built: set[str] = set()
        for name in builders:
            tab = ttk.Frame(notebook, padding=12, style="ModernCard.TFrame")
            tabs[name] = tab
            notebook.add(tab, text=name, sticky="nsew")

        def build_selected(*_args):
            selected = notebook.select()
            if not selected:
                return
            tab = window.nametowidget(selected)
            name = str(notebook.tab(tab, "text"))
            if name in built:
                return
            built.add(name)
            loading = ttk.Label(tab, text="Loading…", font=("DejaVu Sans", 15, "bold"))
            loading.pack(expand=True)
            window.update_idletasks()
            loading.destroy()
            builders[name](tab)

            def restyle(widget):
                for child in widget.winfo_children():
                    if isinstance(child, ttk.Treeview):
                        child.configure(style="Modern.Treeview")
                    elif isinstance(child, ttk.Button):
                        child.configure(style="Modern.TButton")
                    restyle(child)
            restyle(tab)

        notebook.bind("<<NotebookTabChanged>>", build_selected)
        window.after_idle(build_selected)

    POSOS.manager_screen = manager_screen
    POSOS._posos_fast_manager_patch = True
