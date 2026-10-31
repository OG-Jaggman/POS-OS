# POS OS

POS OS is a lightweight, offline-first touchscreen cash register application for older PCs.

## v2.10.0 highlights

- Touch-first employee PIN login with a large on-screen number pad
- On-screen number entry for PINs, prices, cash received, quantities, and stock
- On-screen QWERTY keyboard for names, categories, searches, and settings
- Physical keyboard, mouse, numpad, and USB barcode-scanner support remain enabled
- Large buttons designed for a register touchscreen
- Manager section for adding, editing, testing, enabling, and deleting receipt printers
- 80 mm and 58 mm receipt layouts
- USB-connected ESC/POS receipt printers through Linux/CUPS
- Linux/CUPS system printer queues through `lp`
- Windows printer queues through optional `pywin32`
- File printer for testing without physical printer hardware
- Default printer selection and optional auto-cut
- Automatic receipt printing after a completed cash sale

## Existing register features

- First-run manager account and PIN creation
- Employee PIN login and manager/cashier roles
- Product names, barcodes, prices, categories, inventory, and low-stock values
- Barcode scanners that behave like keyboards
- No tax calculation; the displayed item price is final
- Cash checkout and change calculation
- Sale history and local SQLite storage
- Full-screen kiosk mode

## Running on Linux

```bash
sudo apt install python3 python3-tk python3-venv cups-client
python3 -m posos
```

To test in a normal window instead of full-screen:

```bash
POSOS_WINDOWED=1 POSOS_DATA_DIR="$PWD/test-data" python3 -m posos
```

## Receipt printer types

Open **Manager → Printers & Drawer**.

### System / CUPS printer

Connect the receipt printer by USB, make sure Linux/CUPS detects it, then enter its CUPS queue name. Leaving the queue blank uses the system default printer. POS OS no longer supports Ethernet/Wi-Fi printer connections.

### Windows printer

Use a Windows printer queue while testing POS OS on Windows. Install the optional package:

```powershell
py -m pip install pywin32
```

Enter the Windows printer queue name, or leave it blank to use the default printer.

### File printer

Writes the receipt to a text file. This is useful for VM testing before connecting a real printer.

## Paper width

- **80 mm:** 48 text characters per line; recommended for the CUSTOM receipt printer
- **58 mm:** 32 text characters per line; intended for narrower older-style printers

## Installing as the POS OS application

```bash
sudo ./scripts/install.sh
```

The application is installed under `/opt/posos`, with register data in `/var/lib/posos`.

## GitHub update release

Run:

```bash
./scripts/make_release.sh
```

This creates:

- `posos-update.tar.gz`
- `posos-update.tar.gz.sha256`
