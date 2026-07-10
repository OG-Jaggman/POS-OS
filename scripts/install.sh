#!/bin/bash
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo "Run with sudo"; exit 1; fi
APP=/opt/posos/versions/$(cat VERSION)
id -u posos >/dev/null 2>&1 || useradd -m -s /bin/bash posos
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-tk python3-pil.imagetk unclutter x11-xserver-utils
mkdir -p "$APP" /var/lib/posos /opt/posos/versions
cp -a posos VERSION requirements.txt "$APP/"
python3 -m venv "$APP/venv"
"$APP/venv/bin/pip" install --no-cache-dir -r requirements.txt || true
ln -sfn "$APP" /opt/posos/current
chown -R posos:posos /var/lib/posos /opt/posos
install -m 0644 systemd/posos.service /etc/systemd/system/posos.service
systemctl daemon-reload
systemctl enable posos.service
