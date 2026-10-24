#!/usr/bin/env bash
# Deprecated: kept so existing cron entries keep working. Use deploy/backup.sh (database + private
# files + manifest, optional encryption) and verify with deploy/restore.sh verify.
set -euo pipefail
exec "$(dirname "$0")/../backup.sh" "$@"
