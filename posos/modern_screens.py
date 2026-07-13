from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


BG = "#f4f3ef"
PANEL = "#ffffff"
SIDEBAR = "#795548"
SIDEBAR_ACTIVE = "#ff9f00"
ACCENT = "#ffa000"
TEXT = "#242424"
MUTED = "#777777"
BORDER = "#dedbd5"


def patch_modern_secondary_screens() -> None:
    from .app import DB, POSOS, verify_pin

    if getattr(POSOS, "_posos_modern_secondary_patch", False):
        return

    original_manager_screen = POSOS.manager_screen

    def configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Modern.TFrame", background=BG)
        style.configure("ModernCard.TFrame", background=PANEL)
        style.configure("Modern.TLabel", background=BG, foreground=TEXT)
        style.configure("ModernCard.TLabel", background=PANEL, foreground=TEXT)
        style.configure("Modern.TNotebook", background=BG, borderwidth=0)
        style.configure(
            "Modern.TNotebook.Tab",
            background=SIDEBAR,
            foreground="white",
            padding=(18, 12),
            font=("DejaVu Sans", 11, "bold"),
        )
        style.map(
            "Modern.TNotebook.Tab",
            background=[("selected", SIDEBAR_ACTIVE), ("active", "#8d6e63")],
            foreground=[("selected", "white")],
        )
        style.configure("Modern.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=38)
        style.configure("Modern.Treeview.Heading", background="#eeeae4", foreground=TEXT, font=("DejaVu Sans", 10, "bold"))
        style.map("Modern.Treeview", background=[("selected", "#ffd180")], foreground=[("selected", TEXT)])
        style.configure("Modern.TButton", padding=(12, 9), font=("DejaVu Sans", 10, "bold"))
        style.configure("Accent.TButton", background=ACCENT, foreground=TEXT, padding=(16, 11), font=("DejaVu Sans", 12, "bold"))
        style.map("Accent.TButton", background=[("active", "#e58b00")])

    def login_screen(self):
        self.clear()
        self.configure(bg=BG)
        configure_styles(self)

        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)

        left = tk.Frame(shell, bg=SIDEBAR, width=360)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        tk.Label(left, text="POS OS", bg=SIDEBAR, fg="white", font=("DejaVu Sans", 34, "bold")).pack(anchor="w", padx=34, pady=(70, 8))
        tk.Label(
            left,
            text="Fast checkout.\nSimple management.\nBuilt for touch.",
            bg=SIDEBAR,
            fg="#f5ede9",
            justify="left",
            font=("DejaVu Sans", 17),
        ).pack(anchor="w", padx=36, pady=(0, 24))
        tk.Frame(left, bg=ACCENT, height=8).pack(fill="x", side="bottom")

        right = tk.Frame(shell, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        card = tk.Frame(right, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        card.place(relx=0.5, rely=0.5, anchor="center", width=520, height=590)

        tk.Label(card, text="Employee Sign In", bg=PANEL, fg=TEXT, font=("DejaVu Sans", 27, "bold")).pack(pady=(28, 4))
        tk.Label(card, text="Enter your employee PIN", bg=PANEL, fg=MUTED, font=("DejaVu Sans", 13)).pack(pady=(0, 14))

        value = tk.StringVar()
        entry = tk.Entry(
            card,
            textvariable=value,
            show="•",
            justify="center",
            bg="#f5f3ef",
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            font=("DejaVu Sans", 28),
        )
        entry.pack(fill="x", padx=55, pady=(0, 16), ipady=10)
        entry.focus_set()

        def press(key: str) -> None:
            if key == "Clear":
                value.set("")
            elif key == "⌫":
                value.set(value.get()[:-1])
            else:
                value.set(value.get() + key)

        def sign_in(*_args) -> None:
            for employee in DB.employee_by_pin_candidates():
                if verify_pin(value.get(), employee["pin_hash"]):
                    self.current_user = employee
                    self.register_screen()
                    return
            value.set("")
            messagebox.showerror("Login failed", "Incorrect or disabled employee PIN.")

        keypad = tk.Frame(card, bg=PANEL)
        keypad.pack(fill="both", expand=True, padx=48)
        keys = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["Clear", "0", "⌫"]]
        for row_index, row in enumerate(keys):
            keypad.grid_rowconfigure(row_index, weight=1)
            for column_index, key in enumerate(row):
                keypad.grid_columnconfigure(column_index, weight=1)
                background = "#ece9e3" if key not in {"Clear", "⌫"} else "#f7e7df"
                foreground = TEXT if key not in {"Clear", "⌫"} else "#c44d23"
                tk.Button(
                    keypad,
                    text=key,
                    command=lambda selected=key: press(selected),
                    bg=background,
                    fg=foreground,
                    activebackground="#ffd180",
                    relief="flat",
                    font=("DejaVu Sans", 16, "bold"),
                ).grid(row=row_index, column=column_index, sticky="nsew", padx=5, pady=5)

        tk.Button(
            card,
            text="SIGN IN",
            command=sign_in,
            bg=ACCENT,
            fg=TEXT,
            activebackground="#e58b00",
            relief="flat",
            font=("DejaVu Sans", 15, "bold"),
        ).pack(fill="x", padx=48, pady=18, ipady=12)
        entry.bind("<Return>", sign_in)

    def manager_screen(self):
        if self.current_user["role"] != "manager":
            return
        self.clear()
        self.configure(bg=BG)
        configure_styles(self)

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
            command=self.register_screen,
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

        notebook = ttk.Notebook(body, style="Modern.TNotebook")
        notebook.pack(fill="both", expand=True)
        names = ("Items", "Employees", "Sales", "Printers & Drawer", "System")
        tabs = {name: ttk.Frame(notebook, padding=12, style="ModernCard.TFrame") for name in names}
        for name, tab in tabs.items():
            notebook.add(tab, text=name, sticky="nsew")

        self.build_items_tab(tabs["Items"])
        self.build_employees_tab(tabs["Employees"])
        self.build_sales_tab(tabs["Sales"])
        self.build_printers_tab(tabs["Printers & Drawer"])
        self.build_system_tab(tabs["System"])

        def restyle(widget) -> None:
            for child in widget.winfo_children():
                if isinstance(child, ttk.Treeview):
                    child.configure(style="Modern.Treeview")
                elif isinstance(child, ttk.Button):
                    child.configure(style="Modern.TButton")
                restyle(child)

        restyle(body)

    POSOS.login_screen = login_screen
    POSOS.manager_screen = manager_screen
    POSOS._posos_modern_secondary_patch = True
