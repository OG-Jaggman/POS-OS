# POSOS

POSOS is a lightweight, offline-first cash register application designed for older PCs.

## Included

- First-run manager PIN creation
- Employee PIN login and roles
- Add, edit, disable, and remove employees
- Add, edit, disable, and remove items
- Barcode, price, category, inventory quantity, and low-stock level
- Barcode-scanner input (USB scanners that act like keyboards)
- No tax system: the listed item price is the final price
- Cash checkout and change calculation
- Completed-sale history and receipt reprints
- Local SQLite storage
- Database backup before updates
- GitHub Releases updater with SHA-256 verification and rollback-friendly version folders
- Full-screen kiosk mode

## Run on a normal Linux computer

```bash
sudo apt install python3 python3-tk python3-pil.imagetk
python3 -m posos
```

On first launch, POSOS requires a manager name and PIN. The PIN is stored using Python's `scrypt` password hashing, never as readable text.

## GitHub update releases

Set `github_repo` in `/var/lib/posos/config.json` to `OWNER/REPOSITORY`.

Each GitHub Release should contain:

- `posos-update.tar.gz`
- `posos-update.tar.gz.sha256`

The archive should contain the application files with `VERSION` at its root. POSOS downloads releases only after a manager approves the update.

## Install as a system application

```bash
sudo ./scripts/install.sh
sudo systemctl enable --now posos.service
```

The OS builder package installs this repository automatically.
