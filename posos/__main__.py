from .app import main
from .refunds import patch_sales_tab

patch_sales_tab()

if __name__ == "__main__":
    main()
