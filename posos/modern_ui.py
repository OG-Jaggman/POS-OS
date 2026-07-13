from __future__ import annotations

import tkinter as tk
from tkinter import ttk


BG = "#f4f3ef"
PANEL = "#ffffff"
SIDEBAR = "#795548"
SIDEBAR_ACTIVE = "#ff9f00"
ACCENT = "#ffa000"
ACCENT_DARK = "#e58b00"
TEXT = "#242424"
MUTED = "#777777"
DANGER = "#d84315"
BORDER = "#dedbd5"


def patch_modern_register_ui() -> None:
    from .app import DB, POSOS, money

    if getattr(POSOS, "_posos_modern_ui_patch", False):
        return

    def configure_styles(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("POS.Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=56, borderwidth=0)
        style.configure("POS.Treeview.Heading", background="#f0eee9", foreground=TEXT, relief="flat", font=("DejaVu Sans", 10, "bold"))
        style.map("POS.Treeview", background=[("selected", "#ffd180")], foreground=[("selected", TEXT)])

    def register_screen(self):
        self.clear()
        self.cart = {}
        self.configure(bg=BG)
        configure_styles(self)

        # Header
        header = tk.Frame(self, bg=PANEL, height=58, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="POS OS", bg=PANEL, fg=TEXT, font=("DejaVu Sans", 22, "bold")).pack(side="left", padx=(18, 22))

        search_var = tk.StringVar()
        search_wrap = tk.Frame(header, bg="#f1f1ef", highlightbackground=BORDER, highlightthickness=1)
        search_wrap.pack(side="left", fill="x", expand=True, padx=(0, 18), pady=10)
        search_entry = tk.Entry(search_wrap, textvariable=search_var, bd=0, bg="#f1f1ef", fg=TEXT, font=("DejaVu Sans", 14))
        search_entry.pack(side="left", fill="both", expand=True, padx=12, pady=5)
        tk.Button(search_wrap, text="⌨", bd=0, bg="#f1f1ef", activebackground="#e6e4df", command=lambda: self._set_from_dialog(search_var, self.ask_text("Search", "Product name or barcode", search_var.get()))).pack(side="right", padx=7)

        user_text = f"{self.current_user['name']}\n{self.current_user['role'].title()}"
        tk.Label(header, text=user_text, bg=PANEL, fg=TEXT, justify="right", font=("DejaVu Sans", 10, "bold")).pack(side="left", padx=(0, 10))
        if self.current_user["role"] == "manager":
            tk.Button(header, text="Manager", bg="#eeeeeb", fg=TEXT, relief="flat", command=self.manager_screen, padx=12, pady=8).pack(side="left", padx=4)
        tk.Button(header, text="Log out", bg="#eeeeeb", fg=TEXT, relief="flat", command=self.login_screen, padx=12, pady=8).pack(side="left", padx=(4, 14))

        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True)
        main.grid_rowconfigure(0, weight=1)
        main.grid_columnconfigure(0, weight=0, minsize=145)
        main.grid_columnconfigure(1, weight=3)
        main.grid_columnconfigure(2, weight=2, minsize=330)

        # Categories
        categories_frame = tk.Frame(main, bg=SIDEBAR)
        categories_frame.grid(row=0, column=0, sticky="nsew")
        category_var = tk.StringVar(value="All")
        category_buttons: dict[str, tk.Button] = {}

        items_all = list(DB.items(True))
        categories = ["All"] + sorted({str(item["category"] or "General") for item in items_all})

        def select_category(name: str) -> None:
            category_var.set(name)
            for cat, button in category_buttons.items():
                button.configure(bg=SIDEBAR_ACTIVE if cat == name else SIDEBAR, fg="white")
            refresh_products()

        for category in categories:
            button = tk.Button(
                categories_frame,
                text=category,
                anchor="w",
                bg=SIDEBAR_ACTIVE if category == "All" else SIDEBAR,
                fg="white",
                activebackground=SIDEBAR_ACTIVE,
                activeforeground="white",
                relief="flat",
                bd=0,
                font=("DejaVu Sans", 11, "bold"),
                padx=14,
                pady=13,
                command=lambda value=category: select_category(value),
            )
            button.pack(fill="x")
            category_buttons[category] = button

        # Product grid with scrollbar
        products_panel = tk.Frame(main, bg=BG)
        products_panel.grid(row=0, column=1, sticky="nsew", padx=(8, 6), pady=8)
        canvas = tk.Canvas(products_panel, bg=BG, bd=0, highlightthickness=0)
        scrollbar = ttk.Scrollbar(products_panel, orient="vertical", command=canvas.yview)
        products_grid = tk.Frame(canvas, bg=BG)
        window_id = canvas.create_window((0, 0), window=products_grid, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        products_grid.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window_id, width=e.width))

        def refresh_products(*_args) -> None:
            for widget in products_grid.winfo_children():
                widget.destroy()
            query = search_var.get().strip().lower()
            selected_category = category_var.get()
            filtered = []
            for item in DB.items(True):
                if selected_category != "All" and str(item["category"] or "General") != selected_category:
                    continue
                if query and query not in item["name"].lower() and query not in (item["barcode"] or "").lower():
                    continue
                filtered.append(item)

            columns = 4
            for column in range(columns):
                products_grid.grid_columnconfigure(column, weight=1, uniform="product")
            for index, item in enumerate(filtered[:80]):
                card = tk.Frame(products_grid, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
                card.grid(row=index // columns, column=index % columns, sticky="nsew", padx=5, pady=5)
                tk.Label(card, text=money(item["price_cents"]), bg=PANEL, fg="#ef6c00", font=("DejaVu Sans", 12, "bold"), anchor="w").pack(fill="x", padx=10, pady=(9, 4))
                icon = tk.Label(card, text="▦", bg="#efede8", fg="#a69f94", font=("DejaVu Sans", 28), height=2)
                icon.pack(fill="x", padx=10, pady=3)
                tk.Label(card, text=item["name"], bg=PANEL, fg=TEXT, font=("DejaVu Sans", 10, "bold"), wraplength=125, justify="center").pack(fill="x", padx=8, pady=(5, 10))
                for child in card.winfo_children():
                    child.bind("<Button-1>", lambda _event, selected=item: self.add_item(selected))
                card.bind("<Button-1>", lambda _event, selected=item: self.add_item(selected))

        search_var.trace_add("write", refresh_products)
        search_entry.bind("<Return>", lambda _event: (self.scan_or_search(search_var.get()), search_var.set("")))

        # Cart panel
        cart_panel = tk.Frame(main, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        cart_panel.grid(row=0, column=2, sticky="nsew", padx=(0, 8), pady=8)
        cart_panel.grid_rowconfigure(1, weight=1)
        cart_panel.grid_columnconfigure(0, weight=1)

        cart_header = tk.Frame(cart_panel, bg=PANEL)
        cart_header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 5))
        tk.Label(cart_header, text="Current Order", bg=PANEL, fg=TEXT, font=("DejaVu Sans", 16, "bold")).pack(side="left")
        self.cart_count_label = tk.Label(cart_header, text="0 items", bg=PANEL, fg=MUTED, font=("DejaVu Sans", 10))
        self.cart_count_label.pack(side="right")

        self.cart_tree = ttk.Treeview(cart_panel, columns=("qty", "price", "total"), show="tree headings", style="POS.Treeview")
        self.cart_tree.heading("#0", text="Item")
        self.cart_tree.heading("qty", text="Qty")
        self.cart_tree.heading("price", text="Each")
        self.cart_tree.heading("total", text="Total")
        self.cart_tree.column("#0", width=165)
        self.cart_tree.column("qty", width=48, anchor="center")
        self.cart_tree.column("price", width=72, anchor="e")
        self.cart_tree.column("total", width=78, anchor="e")
        self.cart_tree.grid(row=1, column=0, sticky="nsew", padx=8)

        quantity_bar = tk.Frame(cart_panel, bg=PANEL)
        quantity_bar.grid(row=2, column=0, sticky="ew", padx=8, pady=7)
        for text, command, color in (
            ("−", lambda: self.change_quantity(-1), "#eeeeeb"),
            ("+", lambda: self.change_quantity(1), "#eeeeeb"),
            ("Remove", self.remove_selected, "#ffebe5"),
        ):
            tk.Button(quantity_bar, text=text, command=command, bg=color, fg=TEXT if text != "Remove" else DANGER, relief="flat", font=("DejaVu Sans", 11, "bold"), pady=7).pack(side="left", fill="x", expand=True, padx=3)

        totals = tk.Frame(cart_panel, bg="#faf9f6")
        totals.grid(row=3, column=0, sticky="ew", padx=8, pady=(0, 8))
        self.total_label = tk.Label(totals, text="Total: $0.00", bg="#faf9f6", fg=TEXT, font=("DejaVu Sans", 23, "bold"), anchor="e")
        self.total_label.pack(fill="x", padx=12, pady=12)

        # Bottom action bar inspired by the reference layout.
        bottom = tk.Frame(self, bg=SIDEBAR, height=70)
        bottom.pack(fill="x")
        bottom.pack_propagate(False)
        action_area = tk.Frame(bottom, bg=SIDEBAR)
        action_area.pack(side="left", fill="both", expand=True)
        actions = [
            ("Saved Orders", getattr(self, "open_saved_orders", lambda: None)),
            ("Save Order", getattr(self, "save_current_order", lambda: None)),
            ("Clear", self.clear_sale),
        ]
        for text, command in actions:
            tk.Button(action_area, text=text, command=command, bg=SIDEBAR, fg="white", activebackground="#6d4c41", activeforeground="white", relief="flat", font=("DejaVu Sans", 12, "bold"), padx=20).pack(side="left", fill="both", expand=True)

        pay_button = tk.Button(bottom, text="PAY\n$0.00", command=self.cash_payment, bg=ACCENT, fg=TEXT, activebackground=ACCENT_DARK, relief="flat", font=("DejaVu Sans", 18, "bold"), width=15)
        pay_button.pack(side="right", fill="y")
        self.pay_button = pay_button

        original_refresh_cart = self.refresh_cart

        def refresh_cart_modern() -> None:
            original_refresh_cart()
            count = sum(line["qty"] for line in self.cart.values())
            total = sum(line["qty"] * line["price_cents"] for line in self.cart.values())
            self.cart_count_label.configure(text=f"{count} item" if count == 1 else f"{count} items")
            self.pay_button.configure(text=f"PAY\n{money(total)}")

        self.refresh_cart = refresh_cart_modern
        refresh_products()
        self.refresh_cart()
        search_entry.focus_set()

    POSOS.register_screen = register_screen
    POSOS._posos_modern_ui_patch = True
