#!/usr/bin/env bash
# ==========================================================================
# zed-downloader — management CLI.
#
# Installed by scripts/install.sh as /usr/local/bin/zed-downloader.
# Override the app directory with ZED_DIR (default /opt/zed-downloader).
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
# NOTE: --env-file makes compose interpolate ${VAR}s from $APP_DIR/.env.
# We deliberately do NOT use --project-directory: it would re-anchor the
# relative env_file/build paths inside the compose file (../.env) away
# from the deploy/ directory and break them.
COMPOSE=(docker compose -f "$APP_DIR/deploy/docker-compose.yml")
if [[ -f "$ENV_FILE" ]]; then
    COMPOSE+=(--env-file "$ENV_FILE")
fi

# Read one KEY=VALUE from .env without sourcing the whole file.
env_get() {
    grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -n1 | cut -d= -f2- || true
}

# NOTE: the API port is not published on the host, so health probes run
# inside the api container.
api_health() {
    "${COMPOSE[@]}" exec -T api curl -fsS http://localhost:8000/health 2>/dev/null
}

# redis is password-protected (--requirepass). The redis container exports
# REDISCLI_AUTH, so redis-cli inside it auto-authenticates — no need to pass
# the password here. Grep for PONG instead of trusting redis-cli's exit code:
# a bare `redis-cli ping` can exit 0 while printing a NOAUTH error, so it must
# NOT be used as the health signal directly.
redis_ping() {
    "${COMPOSE[@]}" exec -T redis redis-cli ping 2>/dev/null | grep -q PONG
}

require_env() {
    [[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE — run scripts/install.sh first."
}

# ------------------------------------------------------------- subcommands
cmd_status() {
    "${COMPOSE[@]}" ps
    echo
    if out="$(api_health)"; then
        log "API health: OK ${out:+($out)}"
    else
        err "API health: FAILING (try: zed-downloader logs api)"
    fi
}

cmd_logs() {
    # Usage: logs [--follow|-f] [service]
    # Default: print the last 200 lines and EXIT (never hangs). Pass --follow
    # (or -f) to stream. This keeps `zed-downloader logs api` returnable.
    local follow=0
    local args=()
    for a in "$@"; do
        case "$a" in
            -f|--follow) follow=1 ;;
            *) args+=("$a") ;;
        esac
    done
    if [[ "$follow" -eq 1 ]]; then
        "${COMPOSE[@]}" logs -f --tail=200 "${args[@]}"
    else
        "${COMPOSE[@]}" logs --tail=200 "${args[@]}"
    fi
}

cmd_start() {
    log "starting stack"
    "${COMPOSE[@]}" up -d
}

cmd_stop() {
    log "stopping stack"
    "${COMPOSE[@]}" stop
}

cmd_restart() {
    # Usage: restart [service]
    if [[ $# -gt 0 ]]; then
        log "restarting: $*"
    else
        log "restarting all services"
    fi
    "${COMPOSE[@]}" restart "$@"
}

cmd_update() {
    # One-line updater: `zed-downloader update` — backup, pull, rebuild,
    # health gate, auto-rollback of code + DB on failure. See docs/UPDATE.md.
    exec bash "$APP_DIR/scripts/update.sh"
}

cmd_backup() {
    exec bash "$APP_DIR/scripts/backup.sh"
}

cmd_restore() {
    [[ $# -ge 1 ]] || die "usage: zed-downloader restore <backup.tar.gz>"
    exec bash "$APP_DIR/scripts/restore.sh" "$1"
}

cmd_set_webhook() {
    require_env
    local token domain secret
    token="$(env_get BOT_TOKEN)"
    domain="$(env_get DOMAIN)"
    secret="$(env_get TELEGRAM_WEBHOOK_SECRET)"
    [[ -n "$token" && -n "$domain" && -n "$secret" ]] \
        || die "BOT_TOKEN, DOMAIN and TELEGRAM_WEBHOOK_SECRET must be set in $ENV_FILE"

    log "registering Telegram webhook: https://${domain}/webhook/telegram"
    curl -fsS "https://api.telegram.org/bot${token}/setWebhook" \
        --data-urlencode "url=https://${domain}/webhook/telegram" \
        --data-urlencode "secret_token=${secret}"
    echo
    log "now set RUN_MODE=webhook in $ENV_FILE and run: zed-downloader restart bot"
    log "to go back to polling: zed-downloader delete-webhook (and RUN_MODE=polling)"
}

cmd_delete_webhook() {
    require_env
    local token
    token="$(env_get BOT_TOKEN)"
    [[ -n "$token" ]] || die "BOT_TOKEN must be set in $ENV_FILE"
    log "deleting Telegram webhook"
    curl -fsS "https://api.telegram.org/bot${token}/deleteWebhook"
    echo
    log "set RUN_MODE=polling in $ENV_FILE and run: zed-downloader restart bot"
}

cmd_doctor() {
    local failures=0
    check() {
        # check "label" cmd args...
        local label="$1"
        shift
        if "$@" >/dev/null 2>&1; then
            echo "  [${C_GREEN}OK${C_RESET}]   $label"
        else
            echo "  [${C_RED}FAIL${C_RESET}] $label"
            failures=$((failures + 1))
        fi
    }

    log "running diagnostics"
    check "docker daemon running"        docker info
    check ".env exists ($ENV_FILE)"      test -f "$ENV_FILE"
    check "compose file readable"        test -f "$APP_DIR/deploy/docker-compose.yml"
    check "api /health responding"       api_health
    check "postgres accepting connections" \
        "${COMPOSE[@]}" exec -T postgres pg_isready -U "$(env_get POSTGRES_USER)"
    check "redis responding to PING" redis_ping

    echo
    log "container states:"
    "${COMPOSE[@]}" ps || true

    echo
    log "disk space:"
    df -h / || true

    echo
    if [[ "$failures" -eq 0 ]]; then
        log "doctor: all checks passed"
    else
        err "doctor: $failures check(s) failed"
        exit 1
    fi
}

cmd_version() {
    echo "version: $(cat "$APP_DIR/VERSION" 2>/dev/null || echo unknown)"
    echo "commit:  $(git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || echo unknown)"
}

cmd_reset_db() {
    # Recovery for the classic "API can't authenticate to Postgres" failure:
    # Postgres bakes its password into the data volume at first init and
    # ignores POSTGRES_PASSWORD forever after, so a regenerated password in
    # .env no longer matches. Removing the volume lets it re-init cleanly.
    require_env
    warn "reset-db DELETES ALL DATABASE DATA (users, subscriptions, payments, downloads)."
    if [[ "${FORCE:-0}" != "1" ]]; then
        printf "Type 'yes' to continue: "
        read -r ans
        [[ "$ans" == "yes" ]] || die "aborted"
    fi
    log "stopping the stack"
    "${COMPOSE[@]}" down
    # Compose project name is pinned to 'zed-downloader' in the compose file.
    local vol="zed-downloader_postgres_data"
    log "removing postgres volume: $vol"
    docker volume rm "$vol" >/dev/null 2>&1 || warn "volume $vol not found (already removed?)"
    log "starting the stack — postgres re-initializes with the current .env password"
    "${COMPOSE[@]}" up -d --build
    log "done. Watch it come up with: zed-downloader status"
}

usage() {
    cat <<EOF
zed-downloader — management CLI (app dir: $APP_DIR)

Usage: zed-downloader <command> [args]

Commands:
  status              Container list + API health
  logs [--follow] [svc]  Last 200 log lines and exit; --follow to stream
  start               Start the whole stack (docker compose up -d)
  stop                Stop all containers
  restart [service]   Restart everything, or one service
  update              Update to the latest version (backup, rebuild, health-check, auto-rollback)
  backup              Dump database + .env + VERSION into a tar.gz
  restore FILE        Restore a backup archive (destructive, asks to confirm)
  set-webhook         Register the Telegram webhook for RUN_MODE=webhook
  delete-webhook      Remove the Telegram webhook (back to polling)
  doctor              Run health diagnostics
  reset-db            Recreate the Postgres volume (DESTROYS data) — fixes a
                      password mismatch after regenerating secrets
  version             Show app version and git commit
  help                Show this help

Environment:
  ZED_DIR             App directory (default /opt/zed-downloader)
EOF
}

# ------------------------------------------------------------------- main
main() {
    local cmd="${1:-help}"
    shift || true
    case "$cmd" in
        status)          cmd_status "$@" ;;
        logs)            cmd_logs "$@" ;;
        start)           cmd_start "$@" ;;
        stop)            cmd_stop "$@" ;;
        restart)         cmd_restart "$@" ;;
        update)          cmd_update "$@" ;;
        backup)          cmd_backup "$@" ;;
        restore)         cmd_restore "$@" ;;
        set-webhook)     cmd_set_webhook "$@" ;;
        delete-webhook)  cmd_delete_webhook "$@" ;;
        doctor)          cmd_doctor "$@" ;;
        reset-db)        cmd_reset_db "$@" ;;
        version)         cmd_version "$@" ;;
        help|-h|--help)  usage ;;
        *)
            err "unknown command: $cmd"
            echo
            usage
            exit 1
            ;;
    esac
}

main "$@"
