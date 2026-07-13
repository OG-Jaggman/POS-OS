from .app import main
from .refunds import patch_sales_tab
from .saved_orders import patch_register_saved_orders

patch_sales_tab()
patch_register_saved_orders()

if __name__ == "__main__":
    main()
