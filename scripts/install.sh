#!/bin/bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Run with sudo"
  exit 1
fi

APP=/opt/posos/versions/$(tr -d '[:space:]' < VERSION)
id -u register >/dev/null 2>&1 || useradd -m -s /bin/bash register
mkdir -p "$APP" /var/lib/posos /opt/posos/versions
cp -a posos VERSION requirements.txt "$APP/"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --no-cache-dir -r "$APP/requirements.txt"
ln -sfn "$APP" /opt/posos/current

install -m 0755 scripts/posos-install-update /usr/local/sbin/posos-install-update
cat >/etc/sudoers.d/posos-updater <<'SUDOERS'
register ALL=(root) NOPASSWD: /usr/local/sbin/posos-install-update
SUDOERS
chmod 0440 /etc/sudoers.d/posos-updater

# Importing the updater as root installs the restricted Wi-Fi repair permission
# and repairs Debian's CD-ROM-only package source configuration when needed.
POSOS_DATA_DIR=/var/lib/posos PYTHONPATH="$APP" \
  "$APP/venv/bin/python" -c 'import posos.updater'

chown -R register:register /var/lib/posos /opt/posos
