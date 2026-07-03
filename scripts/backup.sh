#!/usr/bin/env bash
# ==========================================================================
# zed-downloader — backup.
#
# Creates BACKUP_DIR/zed-backup-YYYYmmdd-HHMMSS.tar.gz containing:
#   db.sql   full pg_dump of the application database
#   .env     current environment/secrets
#   VERSION  app version at backup time
# Keeps only the newest 10 archives. Prints the archive path last.
# ==========================================================================
set -euo pipefail

C_GREEN=$'\033[1;32m'
C_YELLOW=$'\033[1;33m'
C_RED=$'\033[1;31m'
C_RESET=$'\033[0m'

log()  { echo "${C_GREEN}[zed]${C_RESET} $*"; }
warn() { echo "${C_YELLOW}[zed] WARN:${C_RESET} $*" >&2; }
err()  { echo "${C_RED}[zed] ERROR:${C_RESET} $*" >&2; }
die()  { err "$*"; exit 1; }

APP_DIR="${ZED_DIR:-/opt/zed-downloader}"
ENV_FILE="$APP_DIR/.env"
BACKUP_DIR="${BACKUP_DIR:-/opt/zed-downloader/backups}"
# NOTE: --env-file (not --project-directory) so ${VAR} interpolation reads
# the root .env while relative paths inside the compose file stay anchored
# to deploy/.
COMPOSE=(docker compose -f "$APP_DIR/deploy/docker-compose.yml")
if [[ -f "$ENV_FILE" ]]; then
    COMPOSE+=(--env-file "$ENV_FILE")
fi

env_get() {
    grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2- || true
}

[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE — nothing to back up."

PG_USER="$(env_get POSTGRES_USER)"; PG_USER="${PG_USER:-zed}"
PG_DB="$(env_get POSTGRES_DB)";     PG_DB="${PG_DB:-zed_downloader}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date +%Y%m%d-%H%M%S)"
ARCHIVE="$BACKUP_DIR/zed-backup-${STAMP}.tar.gz"

TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

log "dumping database ${PG_DB} (user ${PG_USER})"
"${COMPOSE[@]}" exec -T postgres pg_dump -U "$PG_USER" -d "$PG_DB" > "$TMP_DIR/db.sql" \
    || die "pg_dump failed — is the postgres container running? (zed-downloader start)"

cp "$ENV_FILE" "$TMP_DIR/.env"
if [[ -f "$APP_DIR/VERSION" ]]; then
    cp "$APP_DIR/VERSION" "$TMP_DIR/VERSION"
else
    echo "unknown" > "$TMP_DIR/VERSION"
fi

tar -czf "$ARCHIVE" -C "$TMP_DIR" db.sql .env VERSION
chmod 600 "$ARCHIVE"

# Rotation: keep only the newest 10 archives.
(ls -1t "$BACKUP_DIR"/zed-backup-*.tar.gz 2>/dev/null || true) | tail -n +11 | xargs -r rm -f

log "backup complete ($(du -h "$ARCHIVE" | cut -f1))"
echo "$ARCHIVE"
