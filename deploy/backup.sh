#!/usr/bin/env bash
# Steward backup: PostgreSQL (custom format) + private file storage + manifest with checksums.
#
#   deploy/backup.sh [OUT_DIR]            # default /opt/steward-backups
#
# Environment (optional):
#   COMPOSE="docker compose"               # e.g. "docker compose -p steward --env-file /opt/live-agent/.env"
#   BACKUP_AGE_RECIPIENT=age1...           # encrypt with age (public key only on the server)
#   BACKUP_KEEP_DAYS=14                    # opt-in pruning of THIS script's older backups (unset = keep all)
#
# Output: OUT_DIR/steward-<UTC stamp>/{db.dump, storage.tar.gz, manifest.json}[.age]
# A backup is only trustworthy after deploy/restore.sh has verified it (run that regularly).
set -euo pipefail
umask 077

OUT_ROOT="${1:-/opt/steward-backups}"
COMPOSE="${COMPOSE:-docker compose}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DIR="$OUT_ROOT/steward-$STAMP"
mkdir -p "$DIR"
chmod 700 "$OUT_ROOT" "$DIR"

echo "[backup] database → $DIR/db.dump"
$COMPOSE exec -T db pg_dump -U postgres --format=custom --no-owner --compress=6 steward > "$DIR/db.dump"

echo "[backup] private file storage → $DIR/storage.tar.gz"
# The API container mounts the storage volume at /data (read-only root FS; tar writes to stdout only).
$COMPOSE exec -T api tar -C /data -czf - storage > "$DIR/storage.tar.gz"

echo "[backup] manifest"
counts="$($COMPOSE exec -T db psql -U postgres -d steward -Atc \
  "SELECT json_build_object(
     'alembic_version', (SELECT version_num FROM alembic_version),
     'users', (SELECT count(*) FROM users),
     'workspaces', (SELECT count(*) FROM workspaces),
     'tasks', (SELECT count(*) FROM tasks),
     'files', (SELECT count(*) FROM files),
     'audit_events', (SELECT count(*) FROM audit_events),
     'approval_requests', (SELECT count(*) FROM approval_requests))")"
files_in_tar="$(tar -tzf "$DIR/storage.tar.gz" | grep -vc '/$' || true)"
cat > "$DIR/manifest.json" <<JSON
{
  "created_utc": "$STAMP",
  "db_dump_sha256": "$(sha256sum "$DIR/db.dump" | cut -d' ' -f1)",
  "storage_tar_sha256": "$(sha256sum "$DIR/storage.tar.gz" | cut -d' ' -f1)",
  "storage_objects": $files_in_tar,
  "row_counts": $counts
}
JSON

if [ -n "${BACKUP_AGE_RECIPIENT:-}" ]; then
  command -v age >/dev/null || { echo "[backup] BACKUP_AGE_RECIPIENT set but 'age' is not installed" >&2; exit 1; }
  for f in db.dump storage.tar.gz; do
    age -r "$BACKUP_AGE_RECIPIENT" -o "$DIR/$f.age" "$DIR/$f" && rm -f "$DIR/$f"
  done
  echo "[backup] encrypted with age (private key must be kept OFF this server)"
fi

if [ -n "${BACKUP_KEEP_DAYS:-}" ]; then
  echo "[backup] pruning steward-* backups older than $BACKUP_KEEP_DAYS days in $OUT_ROOT"
  find "$OUT_ROOT" -maxdepth 1 -type d -name 'steward-*' -mtime +"$BACKUP_KEEP_DAYS" -print -exec rm -rf {} +
fi

echo "[backup] done: $DIR"
cat "$DIR/manifest.json"
