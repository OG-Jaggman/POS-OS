from __future__ import annotations

from tkinter import ttk

from . import internet


def _button_texts(frame) -> set[str]:
    texts: set[str] = set()
    for child in frame.winfo_children():
        if isinstance(child, ttk.Button):
            texts.add(str(child.cget("text")))
    return texts


def _fix_internet_layout(parent) -> None:
    tree = None
    controls = None
    note = None

    for child in parent.winfo_children():
        if isinstance(child, ttk.Treeview):
            tree = child
        elif isinstance(child, ttk.Frame):
            texts = _button_texts(child)
            if "Refresh" in texts and "Save Diagnostic" in texts:
                controls = child
        elif isinstance(child, ttk.Label):
            text = str(child.cget("text"))
            if text.startswith("USB tethering appears as Ethernet"):
                note = child

    if tree is None or controls is None:
        return

    # Repack the lower section so the controls reserve space before the
    # Wi-Fi list expands. On short touchscreen displays the old order let the
    # empty Wi-Fi list consume the entire remaining height.
    tree.pack_forget()
    controls.pack_forget()
    if note is not None:
        note.pack_forget()

    if note is not None:
        note.pack(side="bottom", fill="x", anchor="w", pady=(6, 0))

    controls.pack(side="bottom", fill="x", pady=(8, 0))

    buttons = [child for child in controls.winfo_children() if isinstance(child, ttk.Button)]
    for button in buttons:
        button.pack_forget()
    for index, button in enumerate(buttons):
        row, column = divmod(index, 4)
        button.grid(row=row, column=column, sticky="nsew", padx=2, pady=2, ipady=6)
    for column in range(4):
        controls.columnconfigure(column, weight=1)

    tree.configure(height=5)
    tree.pack(fill="both", expand=True)


def patch_internet_layout() -> None:
    original = internet.build_internet_tab
    if getattr(original, "_posos_layout_fix", False):
        return

    def wrapped(root, parent) -> None:
        original(root, parent)
        _fix_internet_layout(parent)

    wrapped._posos_layout_fix = True
    internet.build_internet_tab = wrapped
