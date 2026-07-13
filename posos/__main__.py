from .app import main
from .refunds import patch_sales_tab
from .saved_orders import patch_register_saved_orders
from .ui_fixes import patch_cart_selection
from .giftcards import patch_gift_card_manager_tab, patch_payment_screen
from .system_controls import patch_system_controls
from .modern_ui import patch_modern_register_ui
from .modern_ui_runtime import patch_modern_register_runtime
from .modern_screens import patch_modern_secondary_screens

patch_sales_tab()
patch_register_saved_orders()
patch_cart_selection()
patch_gift_card_manager_tab()
patch_payment_screen()
patch_system_controls()
patch_modern_register_ui()
patch_modern_register_runtime()
patch_modern_secondary_screens()

if __name__ == "__main__":
    main()
