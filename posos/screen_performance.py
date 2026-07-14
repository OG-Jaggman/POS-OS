from __future__ import annotations

import tkinter as tk
from tkinter import ttk


BG = "#f4f3ef"
PANEL = "#ffffff"
ACCENT = "#ffa000"
TEXT = "#242424"
MUTED = "#777777"
BORDER = "#dedbd5"


def patch_screen_performance() -> None:
    from .app import POSOS

    if getattr(POSOS, "_posos_screen_performance_patch", False):
        return

    original_register = POSOS.register_screen

    def transition_to_register(self):
        self.clear()
        self.configure(bg=BG)
        frame = tk.Frame(self, bg=BG)
        frame.pack(fill="both", expand=True)
        tk.Label(frame, text="Loading Register…", bg=BG, fg=TEXT, font=("DejaVu Sans", 24, "bold")).place(relx=0.5, rely=0.47, anchor="center")
        tk.Label(frame, text="Preparing products and checkout", bg=BG, fg=MUTED, font=("DejaVu Sans", 12)).place(relx=0.5, rely=0.54, anchor="center")
        self.update_idletasks()
        self.after(20, lambda: original_register(self))

    def manager_screen(self):
        if not self.current_user or self.current_user["role"] != "manager":
            return

        self.clear()
        self.configure(bg=BG)

        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("FastManager.TNotebook", background=BG, borderwidth=0)
        style.configure(
            "FastManager.TNotebook.Tab",
            background="#795548",
            foreground="white",
            padding=(16, 11),
            font=("DejaVu Sans", 10, "bold"),
        )
        style.map(
            "FastManager.TNotebook.Tab",
            background=[("selected", ACCENT), ("active", "#8d6e63")],
            foreground=[("selected", TEXT)],
        )

        header = tk.Frame(self, bg=PANEL, height=64, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Manager Center", bg=PANEL, fg=TEXT, font=("DejaVu Sans", 24, "bold")).pack(side="left", padx=20)
        tk.Label(
            header,
            text=f"Signed in as {self.current_user['name']}",
            bg=PANEL,
            fg=MUTED,
            font=("DejaVu Sans", 10),
        ).pack(side="left", padx=8)
        tk.Button(
            header,
            text="Back to Register",
            command=lambda: transition_to_register(self),
            bg=ACCENT,
            fg=TEXT,
            activebackground="#e58b00",
            relief="flat",
            font=("DejaVu Sans", 11, "bold"),
            padx=16,
            pady=9,
        ).pack(side="right", padx=16)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=12, pady=12)
        notebook = ttk.Notebook(body, style="FastManager.TNotebook")
        notebook.pack(fill="both", expand=True)

        names = ("Items", "Employees", "Sales", "Printers & Drawer", "System")
        tabs = {name: ttk.Frame(notebook, padding=12) for name in names}
        for name in names:
            notebook.add(tabs[name], text=name, sticky="nsew")

        builders = {
            "Items": self.build_items_tab,
            "Employees": self.build_employees_tab,
            "Sales": self.build_sales_tab,
            "Printers & Drawer": self.build_printers_tab,
            "System": self.build_system_tab,
        }
        built: set[str] = set()

        def build_selected(*_):
            selected = notebook.select()
            if not selected:
                return
            tab = notebook.nametowidget(selected)
            name = str(notebook.tab(selected, "text"))
            if name not in builders or name in built:
                return
            built.add(name)
            loading = ttk.Label(tab, text=f"Loading {name}…", font=("DejaVu Sans", 16, "bold"))
            loading.pack(expand=True)
            self.update_idletasks()

            def finish():
                loading.destroy()
                builders[name](tab)

            self.after(10, finish)

        notebook.bind("<<NotebookTabChanged>>", build_selected)
        self.after(10, build_selected)

    POSOS.transition_to_register = transition_to_register
    POSOS.manager_screen = manager_screen
    POSOS._posos_screen_performance_patch = True
