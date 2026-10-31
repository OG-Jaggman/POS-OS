# Changelog

## 2.11.1
- Keep the Checkout action visible on smaller touchscreen displays.
- Improve CUPS receipt-printing error reporting and timeout handling.
- Show clear error messages when test receipt printing or cash-drawer commands fail.
- Cash and POSOS Gift Card remain the only checkout payment methods.


## 2.11.0
- Add a dedicated Checkout button that opens the payment selection menu.
- Add a separate barcode scanner capture field so scanned barcodes add items directly to the cart without filling the product search box.
- Keep product search available independently for manual lookup.

## 2.10.0

- Fixed the Gift Cards manager tab so the lazy-loaded Manager Center builds its registration and balance controls
- Made gift card issuance transactional and added a clear duplicate-card message
- Removed direct Ethernet and raw TCP receipt-printer support
- Switched saved legacy network printer entries to the Linux/CUPS system queue for USB printing
- Updated printer setup guidance for USB-connected printers

## 2.1.0

- Added touch-screen numeric keypad for employee and manager PINs
- Added touch-screen number entry for prices, cash, stock, quantities, and ports
- Added on-screen QWERTY keyboard while preserving physical keyboard support
- Added manager receipt-printer settings
- Added IP/raw TCP ESC/POS printing
- Added Linux/CUPS, Windows queue, and file-test printer modes
- Added 80 mm and 58 mm receipt formatting
- Added default-printer, test-print, enabled, and auto-cut settings
- Added automatic receipt printing after sales
- Added GitHub Actions syntax and receipt-layout tests
