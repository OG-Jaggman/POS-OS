#!/bin/bash
set -euo pipefail
VERSION=$(cat VERSION)
NAME=posos-update.tar.gz
FILES=(posos VERSION requirements.txt config.example.json scripts README.md LICENSE)
tar -czf "$NAME" "${FILES[@]}"
sha256sum "$NAME" > "$NAME.sha256"
echo "Created $NAME and $NAME.sha256 for v$VERSION"
