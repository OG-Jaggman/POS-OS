from __future__ import annotations


def patch_cart_selection() -> None:
    from .app import POSOS

    if getattr(POSOS, "_posos_cart_selection_patch", False):
        return
    original = POSOS.refresh_cart

    def wrapped(self):
        selected = tuple(self.cart_tree.selection()) if hasattr(self, "cart_tree") else ()
        focused = self.cart_tree.focus() if hasattr(self, "cart_tree") else ""
        original(self)
        for item_id in selected:
            if self.cart_tree.exists(item_id):
                self.cart_tree.selection_add(item_id)
        if focused and self.cart_tree.exists(focused):
            self.cart_tree.focus(focused)
            self.cart_tree.see(focused)

    POSOS.refresh_cart = wrapped
    POSOS._posos_cart_selection_patch = True
