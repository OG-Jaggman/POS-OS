from __future__ import annotations


def patch_modern_register_runtime() -> None:
    """Prevent an old screen's cart callback from surviving into a new screen."""
    from .app import POSOS

    if getattr(POSOS, "_posos_modern_runtime_patch", False):
        return

    original = POSOS.register_screen

    def wrapped(self):
        # modern_ui installs a screen-specific refresh callback so it can update
        # the PAY total and item counter. Remove the previous screen's callback
        # before rebuilding the register after payment, logout, or manager use.
        self.__dict__.pop("refresh_cart", None)
        original(self)

    POSOS.register_screen = wrapped
    POSOS._posos_modern_runtime_patch = True
