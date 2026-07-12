#!/bin/bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run with sudo"; exit 1; fi
APP=/opt/posos/versions/$(cat VERSION)
id -u register >/dev/null 2>&1 || useradd -m -s /bin/bash register
mkdir -p "$APP" /var/lib/posos /opt/posos/versions
cp -a posos VERSION requirements.txt "$APP/"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --no-cache-dir -r requirements.txt || true
ln -sfn "$APP" /opt/posos/current
chown -R register:register /var/lib/posos /opt/posos
