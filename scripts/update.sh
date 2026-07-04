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

# --- self-update safety -----------------------------------------------------
# `git reset --hard` below rewrites this very file on disk. Bash reads a script
# lazily as it executes, so replacing it mid-run can corrupt execution. Guard:
# on first entry, copy ourselves to a mktemp file under /tmp and re-exec from
# there (ZED_UPDATE_REEXEC=1 ensures this happens exactly once — no loop).
# Every git/rebuild step then runs from the stable temp copy.
if [[ "${ZED_UPDATE_REEXEC:-0}" != "1" ]]; then
    _self="$0"
    case "$_self" in /*) : ;; *) _self="$(pwd)/$_self" ;; esac
    _copy="$(mktemp /tmp/zed-update.XXXXXX.sh)" \
        || { echo "[zed] ERROR: could not create temp updater copy" >&2; exit 1; }
    cp "$_self" "$_copy" || { echo "[zed] ERROR: could not stage updater copy" >&2; exit 1; }
    chmod +x "$_copy"
    export ZED_UPDATE_REEXEC=1
    export ZED_UPDATE_SELF="$_copy"
    exec bash "$_copy" "$@"
fi
# Running from the temp copy now — delete it when this run ends, however it ends.
trap '[[ -n "${ZED_UPDATE_SELF:-}" ]] && rm -f "$ZED_UPDATE_SELF"' EXIT

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

# /ready may not exist on older deployments. Echo: ok | notready | missing.
api_ready_state() {
    local code
    code="$("${COMPOSE[@]}" exec -T api curl -s -o /dev/null -w '%{http_code}' \
        http://localhost:8000/ready 2>/dev/null || true)"
    case "$code" in
        200) echo ok ;;
        404) echo missing ;;
        *)   echo notready ;;
    esac
}

# Which gate actually passed (for logs/report). Set by wait_healthy.
READY_GATE="/health"

# wait_healthy MAX_TRIES (2s apart). Succeeds only when /health passes AND
# /ready passes too — unless /ready is absent (older build), then /health alone.
wait_healthy() {
    local tries="$1" i state
    for i in $(seq 1 "$tries"); do
        if api_health; then
            state="$(api_ready_state)"
            if [[ "$state" == "ok" ]]; then
                READY_GATE="/health+/ready"
                return 0
            fi
            if [[ "$state" == "missing" ]]; then
                READY_GATE="/health (/ready not present)"
                return 0
            fi
            # state == notready: DB/Redis still warming — keep polling.
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
command -v docker >/dev/null 2>&1 || die "docker is not installed or not on PATH."
[[ -d "$APP_DIR/.git" ]] || die "$APP_DIR is not a git checkout — cannot update."
[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE — run scripts/install.sh first."
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
git fetch origin --prune --tags
git reset --hard "origin/${BRANCH}"

NEW_COMMIT="$(git rev-parse HEAD)"
NEW_VERSION="$(cat VERSION 2>/dev/null || echo unknown)"

if [[ "$NEW_COMMIT" == "$PREV_COMMIT" ]]; then
    log "already up to date (v${PREV_VERSION}) — rebuilding anyway to be safe"
else
    log "updating: v${PREV_VERSION} (${PREV_COMMIT:0:8}) -> v${NEW_VERSION} (${NEW_COMMIT:0:8})"
fi

# Keep APP_VERSION in .env in sync with the pulled VERSION so the image build
# arg and /health report the new version. Update in place, or append if absent.
if [[ -f "$ENV_FILE" ]]; then
    if grep -q '^APP_VERSION=' "$ENV_FILE"; then
        sed -i "s|^APP_VERSION=.*|APP_VERSION=${NEW_VERSION}|" "$ENV_FILE"
    else
        printf 'APP_VERSION=%s\n' "$NEW_VERSION" >> "$ENV_FILE"
    fi
fi

log "step 3/4 — rebuilding and restarting the stack"
"${COMPOSE[@]}" up -d --build

log "step 4/4 — waiting for the API to become healthy (up to ~90s)"
if wait_healthy 45; then
    log "health gate passed: ${READY_GATE}"
    record_update "$PREV_VERSION" "$NEW_VERSION" "success" "cli update"
    echo "UPDATE OK: v${PREV_VERSION} -> v${NEW_VERSION}"
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
    # Last resort: make sure the stack is at least running on the rolled-back
    # code, and point the operator at the logs.
    "${COMPOSE[@]}" up -d --build || true
    err "restore failed or stack still unhealthy after rollback — inspect with: zed-downloader logs api"
fi

record_update "$PREV_VERSION" "$NEW_VERSION" "rolled_back" "cli update failed health check"
echo "UPDATE FAILED — rolled back to v${PREV_VERSION}"
exit 1
