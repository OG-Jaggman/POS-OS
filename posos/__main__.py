from .app import main
from .refunds import patch_sales_tab
from .saved_orders import patch_register_saved_orders
from .modern_ui import patch_modern_register_ui
from .modern_ui_runtime import patch_modern_register_runtime
from .modern_screens import patch_modern_secondary_screens

patch_sales_tab()
patch_register_saved_orders()
patch_modern_register_ui()
patch_modern_register_runtime()
patch_modern_secondary_screens()

if __name__ == "__main__":
    main()
