#!/usr/bin/env bash
# ==========================================================================
# zed-downloader — restore a backup created by scripts/backup.sh.
#
# Usage:
#   restore.sh /opt/zed-downloader/backups/zed-backup-YYYYmmdd-HHMMSS.tar.gz
#   FORCE=1 restore.sh FILE       # skip the confirmation prompt
#
# DESTRUCTIVE: drops and recreates the application database and
# replaces the current .env with the one inside the archive.
# NOTE: this does NOT roll the code back — code versions are managed
# by git via scripts/update.sh.
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

api_health() {
    "${COMPOSE[@]}" exec -T api curl -fsS http://localhost:8000/health >/dev/null 2>&1
}

# ---------------------------------------------------------------- arguments
ARCHIVE="${1:-}"
[[ -n "$ARCHIVE" ]] || die "usage: restore.sh <backup.tar.gz>"
[[ -f "$ARCHIVE" ]] || die "backup file not found: $ARCHIVE"

# ------------------------------------------------------------- confirmation
if [[ "${FORCE:-0}" != "1" ]]; then
    warn "this will OVERWRITE the database and .env with the contents of:"
    warn "  $ARCHIVE"
    read -rp "Type 'yes' to continue: " answer
    [[ "$answer" == "yes" ]] || die "aborted (nothing changed)."
fi

# ------------------------------------------------------------------ extract
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

log "extracting archive"
tar -xzf "$ARCHIVE" -C "$TMP_DIR"
[[ -f "$TMP_DIR/db.sql" ]] || die "invalid backup: db.sql missing from archive."

# -------------------------------------------------------------- restore .env
if [[ -f "$TMP_DIR/.env" ]]; then
    if [[ -f "$ENV_FILE" ]]; then
        keep="$ENV_FILE.pre-restore.$(date +%Y%m%d-%H%M%S)"
        cp "$ENV_FILE" "$keep"
        log "current .env preserved at $keep"
    fi
    cp "$TMP_DIR/.env" "$ENV_FILE"
    chmod 600 "$ENV_FILE"
    log ".env restored from backup"
else
    warn "archive has no .env — keeping the current one"
fi

if [[ -f "$TMP_DIR/VERSION" && -f "$APP_DIR/VERSION" ]]; then
    backup_version="$(cat "$TMP_DIR/VERSION")"
    current_version="$(cat "$APP_DIR/VERSION")"
    if [[ "$backup_version" != "$current_version" ]]; then
        warn "backup was taken on v${backup_version}, current code is v${current_version}"
        warn "schema mismatches are possible — consider checking out the matching release."
    fi
fi

PG_USER="$(env_get POSTGRES_USER)"; PG_USER="${PG_USER:-zed}"
PG_DB="$(env_get POSTGRES_DB)";     PG_DB="${PG_DB:-zed_downloader}"

# ------------------------------------------------------------------ database
log "stopping application services (api, worker, bot) to free db connections"
"${COMPOSE[@]}" stop api worker bot >/dev/null 2>&1 || true

log "starting postgres"
"${COMPOSE[@]}" up -d postgres

log "waiting for postgres to accept connections (up to ~60s)"
pg_ready=0
for _ in $(seq 1 30); do
    if "${COMPOSE[@]}" exec -T postgres pg_isready -U "$PG_USER" >/dev/null 2>&1; then
        pg_ready=1
        break
    fi
    sleep 2
done
[[ "$pg_ready" -eq 1 ]] || die "postgres did not become ready — aborting before touching data."

log "dropping and recreating database ${PG_DB}"
"${COMPOSE[@]}" exec -T postgres psql -U "$PG_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "DROP DATABASE IF EXISTS \"$PG_DB\" WITH (FORCE);"
"${COMPOSE[@]}" exec -T postgres psql -U "$PG_USER" -d postgres -v ON_ERROR_STOP=1 \
    -c "CREATE DATABASE \"$PG_DB\" OWNER \"$PG_USER\";"

log "importing db.sql"
"${COMPOSE[@]}" exec -T postgres psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 \
    < "$TMP_DIR/db.sql" >/dev/null

# ------------------------------------------------------------------ restart
log "rebuilding and restarting the full stack"
"${COMPOSE[@]}" up -d --build

log "waiting for the API to become healthy (up to ~120s)"
healthy=0
for _ in $(seq 1 60); do
    if api_health; then
        healthy=1
        break
    fi
    sleep 2
done

if [[ "$healthy" -eq 1 ]]; then
    log "restore complete — stack is healthy."
else
    err "restore finished but the API is not healthy yet."
    err "inspect with: zed-downloader logs api"
    exit 1
fi
