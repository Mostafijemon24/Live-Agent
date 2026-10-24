#!/usr/bin/env bash
# Logical backup of the Steward database (run on the VPS, e.g. from cron).
# Restores MUST be tested regularly:  gunzip -c <file> | docker compose exec -T db psql -U postgres -d steward_restore_test
set -euo pipefail
OUT_DIR="${1:-./backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
docker compose exec -T db pg_dump -U postgres --no-owner --format=plain steward | gzip > "$OUT_DIR/steward-$STAMP.sql.gz"
chmod 600 "$OUT_DIR/steward-$STAMP.sql.gz"
echo "wrote $OUT_DIR/steward-$STAMP.sql.gz (also back up the 'storage' volume: private uploaded files)"
