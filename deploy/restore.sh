#!/usr/bin/env bash
# Verify or restore a Steward backup made by deploy/backup.sh.
#
#   deploy/restore.sh verify  <BACKUP_DIR>   # NON-destructive: restores into a scratch database
#                                            # (steward_restore_check) and a scratch directory, checks
#                                            # row counts, storage objects and schema ownership against
#                                            # the manifest, then removes the scratch copies.
#   deploy/restore.sh restore <BACKUP_DIR>   # Replaces the live database and storage. Stop the app first.
#                                            # The previous database is KEPT as steward_pre_restore_<UTC>
#                                            # and the previous files as /data/storage.pre-restore, so a
#                                            # bad restore can be rolled back. Nothing is deleted.
#
# Environment: COMPOSE="docker compose ..." (as for backup.sh); AGE_IDENTITY=<key file> if encrypted.
set -euo pipefail
umask 077

MODE="${1:?verify|restore}"
DIR="${2:?backup directory}"
COMPOSE="${COMPOSE:-docker compose}"
[ -f "$DIR/manifest.json" ] || { echo "no manifest.json in $DIR" >&2; exit 1; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
for f in db.dump storage.tar.gz; do
  if [ -f "$DIR/$f.age" ]; then
    : "${AGE_IDENTITY:?backup is encrypted: set AGE_IDENTITY to the private key file}"
    age -d -i "$AGE_IDENTITY" -o "$WORK/$f" "$DIR/$f.age"
  else
    cp "$DIR/$f" "$WORK/$f"
  fi
done

want_db="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["db_dump_sha256"])' "$DIR/manifest.json")"
want_st="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["storage_tar_sha256"])' "$DIR/manifest.json")"
[ "$(sha256sum "$WORK/db.dump" | cut -d' ' -f1)" = "$want_db" ] || { echo "db.dump checksum mismatch" >&2; exit 1; }
[ "$(sha256sum "$WORK/storage.tar.gz" | cut -d' ' -f1)" = "$want_st" ] || { echo "storage checksum mismatch" >&2; exit 1; }
echo "[restore] checksums match the manifest"

psql_su() { $COMPOSE exec -T db psql -v ON_ERROR_STOP=1 -U postgres -q "$@"; }

# Create an empty database laid out exactly like deploy/db/init-roles.sh does, then load the dump
# AS steward_owner (--role) so every object is owned by the migration role, not the superuser.
# (backup.sh dumps with --no-owner; restoring that as postgres would leave tables the app's
# migration role cannot read, and the next `migrate` would fail.)
load_into() {
  local db="$1"
  psql_su -d postgres -c "DROP DATABASE IF EXISTS $db" -c "CREATE DATABASE $db OWNER steward_owner" \
    -c "REVOKE ALL ON DATABASE $db FROM PUBLIC" \
    -c "GRANT CONNECT ON DATABASE $db TO steward_app, steward_worker, steward_deleter, steward_readonly"
  psql_su -d "$db" -c "REVOKE CREATE ON SCHEMA public FROM PUBLIC" -c "ALTER SCHEMA public OWNER TO steward_owner" \
    -c "GRANT USAGE ON SCHEMA public TO steward_app, steward_worker, steward_deleter, steward_readonly"
  $COMPOSE exec -T db pg_restore -U postgres --no-owner --role=steward_owner --exit-on-error --single-transaction \
    -d "$db" < "$WORK/db.dump"
}

summary_sql="SELECT json_build_object(
   'alembic_version', (SELECT version_num FROM alembic_version),
   'users', (SELECT count(*) FROM users),
   'workspaces', (SELECT count(*) FROM workspaces),
   'tasks', (SELECT count(*) FROM tasks),
   'files', (SELECT count(*) FROM files),
   'audit_events', (SELECT count(*) FROM audit_events),
   'approval_requests', (SELECT count(*) FROM approval_requests))"
ownership_sql="SELECT json_build_object(
   'not_owned_by_steward_owner', (SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r','S','i','v','m') AND pg_get_userbyid(c.relowner) <> 'steward_owner'),
   'app_can_read_tasks', has_table_privilege('steward_app', 'tasks', 'SELECT'),
   'app_cannot_delete_tasks', NOT has_table_privilege('steward_app', 'tasks', 'DELETE'),
   'readonly_cannot_write', NOT has_table_privilege('steward_readonly', 'tasks', 'INSERT'))"

if [ "$MODE" = "verify" ]; then
  TARGET=steward_restore_check
  load_into "$TARGET"
  got="$(psql_su -d "$TARGET" -Atc "$summary_sql")"
  own="$(psql_su -d "$TARGET" -Atc "$ownership_sql")"
  mkdir -p "$WORK/storage" && tar -xzf "$WORK/storage.tar.gz" -C "$WORK/storage"
  objects="$(find "$WORK/storage" -type f | wc -l)"
  psql_su -d postgres -c "DROP DATABASE $TARGET"
  python3 - "$DIR/manifest.json" "$got" "$objects" "$own" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
got = json.loads(sys.argv[2])
objects = int(sys.argv[3])
own = json.loads(sys.argv[4])
ok = (got == m["row_counts"] and objects == m["storage_objects"] and own["not_owned_by_steward_owner"] == 0
      and own["app_can_read_tasks"] and own["app_cannot_delete_tasks"] and own["readonly_cannot_write"])
print(json.dumps({"expected": m["row_counts"], "restored": got,
                  "storage_objects_expected": m["storage_objects"], "storage_objects_restored": objects,
                  "ownership_and_grants": own, "result": "VERIFIED" if ok else "MISMATCH"}, indent=2))
sys.exit(0 if ok else 1)
PY
  echo "[restore] verification restore succeeded; scratch database removed"
  exit 0
fi

if [ "$MODE" = "restore" ]; then
  STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
  OLD="steward_pre_restore_$STAMP"
  echo "This REPLACES the live database 'steward' and all stored files with the backup from $DIR."
  echo "The current database is kept as '$OLD' and current files as /data/storage.pre-restore."
  echo "Stop the app first:  $COMPOSE stop web api orchestrator tools deletion scheduler"
  read -r -p "Type 'replace live data' to continue: " answer
  [ "$answer" = "replace live data" ] || { echo "aborted"; exit 1; }

  load_into steward_restore_new
  echo "[restore] backup loaded into steward_restore_new; swapping databases"
  psql_su -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = 'steward' AND pid <> pg_backend_pid()" \
    -c "ALTER DATABASE steward RENAME TO $OLD" \
    -c "ALTER DATABASE steward_restore_new RENAME TO steward" >/dev/null
  # Brings the schema to the current code's head (no-op when the backup is already at head).
  $COMPOSE run --rm -T migrate

  $COMPOSE run --rm --no-deps -T --entrypoint sh api -c \
    'if [ -d /data/storage.pre-restore ]; then echo "/data/storage.pre-restore already exists: move it away first" >&2; exit 1; fi
     mv /data/storage /data/storage.pre-restore 2>/dev/null || true; mkdir -p /data/storage'
  $COMPOSE run --rm --no-deps -T --entrypoint tar api -xzf - -C /data < "$WORK/storage.tar.gz"
  echo "[restore] done."
  echo "  Start the app:  $COMPOSE up -d"
  echo "  Roll back:      stop the app, then in psql (as postgres):"
  echo "                    ALTER DATABASE steward RENAME TO steward_failed_restore_$STAMP;"
  echo "                    ALTER DATABASE $OLD RENAME TO steward;"
  echo "                  and move /data/storage.pre-restore back to /data/storage."
  echo "  When the restored system is confirmed good, remove $OLD and /data/storage.pre-restore yourself."
  exit 0
fi
echo "unknown mode $MODE" >&2
exit 1
