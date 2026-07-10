#!/bin/bash
set -euo pipefail
VERSION=$(cat VERSION)
NAME=posos-update.tar.gz
tar -czf "$NAME" posos VERSION requirements.txt systemd scripts
sha256sum "$NAME" > "$NAME.sha256"
echo "Created $NAME and $NAME.sha256 for v$VERSION"
