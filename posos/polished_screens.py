from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk


BG = "#f4f3ef"
PANEL = "#ffffff"
BROWN = "#795548"
ORANGE = "#ffa000"
TEXT = "#242424"


def patch_polished_screens() -> None:
    from .app import POSOS, verify_pin, DB

    if getattr(POSOS, "_posos_polished_screens_patch", False):
        return

    original_manager = POSOS.manager_screen

    def login_screen(self):
        self.clear()
        self.configure(bg=BG)
        shell = tk.Frame(self, bg=BG)
        shell.pack(fill="both", expand=True)
        card = tk.Frame(shell, bg=PANEL, highlightbackground="#dedbd5", highlightthickness=1, padx=34, pady=28)
        card.place(relx=0.5, rely=0.5, anchor="center", width=470, height=610)
        tk.Label(card, text="POS OS", bg=PANEL, fg=TEXT, font=("DejaVu Sans", 34, "bold")).pack(pady=(0, 4))
        tk.Label(card, text="Employee sign in", bg=PANEL, fg="#777777", font=("DejaVu Sans", 14)).pack(pady=(0, 16))
        value = tk.StringVar()
        entry = tk.Entry(card, textvariable=value, show="•", justify="center", font=("DejaVu Sans", 26), bd=1, relief="solid")
        entry.pack(fill="x", ipady=9, pady=(0, 12))

        def press(key):
            if key == "Clear":
                value.set("")
            elif key == "⌫":
                value.set(value.get()[:-1])
            else:
                value.set(value.get() + key)

        def sign_in(*_):
            for employee in DB.employee_by_pin_candidates():
                if verify_pin(value.get(), employee["pin_hash"]):
                    self.current_user = employee
                    self.register_screen()
                    return
            value.set("")
            messagebox.showerror("Login failed", "Incorrect or disabled employee PIN.")

        keypad = tk.Frame(card, bg=PANEL)
        keypad.pack(fill="both", expand=True)
        rows = [["1", "2", "3"], ["4", "5", "6"], ["7", "8", "9"], ["Clear", "0", "⌫"]]
        for r, row in enumerate(rows):
            keypad.grid_rowconfigure(r, weight=1)
            for c, key in enumerate(row):
                keypad.grid_columnconfigure(c, weight=1)
                tk.Button(keypad, text=key, command=lambda k=key: press(k), bg="#efede8", fg=TEXT, activebackground="#ffd180", relief="flat", font=("DejaVu Sans", 17, "bold")).grid(row=r, column=c, sticky="nsew", padx=4, pady=4)
        tk.Button(card, text="SIGN IN", command=sign_in, bg=ORANGE, fg=TEXT, activebackground="#e58b00", relief="flat", font=("DejaVu Sans", 16, "bold"), pady=13).pack(fill="x", pady=(12, 0))
        entry.bind("<Return>", sign_in)
        entry.focus_set()

    def manager_screen(self):
        original_manager(self)
        self.configure(bg=BG)
        children = self.winfo_children()
        if children:
            top = children[0]
            try:
                top.configure(style="ManagerHeader.TFrame")
                style = ttk.Style(self)
                style.configure("ManagerHeader.TFrame", background=BROWN)
                style.configure("ManagerHeader.TLabel", background=BROWN, foreground="white", font=("DejaVu Sans", 22, "bold"))
                for child in top.winfo_children():
                    if isinstance(child, ttk.Label):
                        child.configure(style="ManagerHeader.TLabel")
            except tk.TclError:
                pass

    POSOS.login_screen = login_screen
    POSOS.manager_screen = manager_screen
    POSOS._posos_polished_screens_patch = True
