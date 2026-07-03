#!/usr/bin/env bash
# ==========================================================================
# zed-downloader — safe updater.
#
# Flow: backup -> git pull latest -> rebuild -> health check.
# On a failed health check the previous commit is restored and the
# stack is rebuilt (automatic rollback). Update outcomes are recorded
# best-effort in the update_history table.
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

# NOTE: API port is not published on the host — probe inside the container.
api_health() {
    "${COMPOSE[@]}" exec -T api curl -fsS http://localhost:8000/health >/dev/null 2>&1
}

# wait_healthy MAX_TRIES (2s apart)
wait_healthy() {
    local tries="$1" i
    for i in $(seq 1 "$tries"); do
        if api_health; then
            return 0
        fi
        sleep 2
    done
    return 1
}

# record_update FROM TO STATUS NOTES — best-effort audit row.
record_update() {
    local from="$1" to="$2" status="$3" notes="$4" pg_user pg_db
    pg_user="$(env_get POSTGRES_USER)"; pg_user="${pg_user:-zed}"
    pg_db="$(env_get POSTGRES_DB)";     pg_db="${pg_db:-zed_downloader}"
    "${COMPOSE[@]}" exec -T postgres psql -U "$pg_user" -d "$pg_db" -c \
        "INSERT INTO update_history (from_version, to_version, status, notes, created_at) VALUES ('$from', '$to', '$status', '$notes', NOW())" \
        >/dev/null 2>&1 \
        || warn "could not record update history (table may not exist yet) — continuing"
}

# --------------------------------------------------------------------- main
[[ -d "$APP_DIR/.git" ]] || die "$APP_DIR is not a git checkout — cannot update."
cd "$APP_DIR"

PREV_COMMIT="$(git rev-parse HEAD)"
PREV_VERSION="$(cat VERSION 2>/dev/null || echo unknown)"
# NOTE: updates track the currently checked-out branch (normally the
# repository default branch).
BRANCH="$(git rev-parse --abbrev-ref HEAD)"

log "current version: ${PREV_VERSION} (${PREV_COMMIT:0:8}, branch ${BRANCH})"

log "step 1/4 — pre-update backup"
# backup.sh prints the archive path as its last stdout line — capture it
# so the rollback path below can restore the database, not just the code.
BACKUP_ARCHIVE="$(bash "$APP_DIR/scripts/backup.sh" | tail -n1)"
[[ -n "$BACKUP_ARCHIVE" && -f "$BACKUP_ARCHIVE" ]] \
    || die "pre-update backup did not produce an archive — refusing to update."
log "pre-update backup: $BACKUP_ARCHIVE"

log "step 2/4 — fetching latest code"
git fetch origin
git reset --hard "origin/${BRANCH}"

NEW_COMMIT="$(git rev-parse HEAD)"
NEW_VERSION="$(cat VERSION 2>/dev/null || echo unknown)"

if [[ "$NEW_COMMIT" == "$PREV_COMMIT" ]]; then
    log "already up to date (v${PREV_VERSION}) — rebuilding anyway to be safe"
else
    log "updating: v${PREV_VERSION} (${PREV_COMMIT:0:8}) -> v${NEW_VERSION} (${NEW_COMMIT:0:8})"
fi

log "step 3/4 — rebuilding and restarting the stack"
"${COMPOSE[@]}" up -d --build

log "step 4/4 — waiting for the API to become healthy (up to ~90s)"
if wait_healthy 45; then
    log "update successful: v${NEW_VERSION}"
    record_update "$PREV_VERSION" "$NEW_VERSION" "success" "cli update"
    exit 0
fi

# ------------------------------------------------------------------ rollback
err "health check failed after update — rolling back to ${PREV_COMMIT:0:8} (v${PREV_VERSION})"
git reset --hard "$PREV_COMMIT"

# Restore the pre-update backup so the database matches the rolled-back
# code (the failed update may have migrated the schema forward).
# restore.sh stops the services, drops/recreates the DB, imports the
# dump, rebuilds the stack and waits for the API health check itself.
log "restoring pre-update backup: $BACKUP_ARCHIVE"
if FORCE=1 bash "$APP_DIR/scripts/restore.sh" "$BACKUP_ARCHIVE"; then
    log "rollback complete — stack healthy again on v${PREV_VERSION}"
else
    err "restore failed or stack still unhealthy after rollback — inspect with: zed-downloader logs api"
fi

record_update "$PREV_VERSION" "$NEW_VERSION" "rolled_back" "cli update failed health check"
exit 1
