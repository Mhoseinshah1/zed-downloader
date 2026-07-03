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
    # Usage: logs [service]
    "${COMPOSE[@]}" logs -f --tail=200 "$@"
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
    check "redis responding to PING" \
        "${COMPOSE[@]}" exec -T redis redis-cli ping

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

usage() {
    cat <<EOF
zed-downloader — management CLI (app dir: $APP_DIR)

Usage: zed-downloader <command> [args]

Commands:
  status              Container list + API health
  logs [service]      Follow logs (last 200 lines); service optional
  start               Start the whole stack (docker compose up -d)
  stop                Stop all containers
  restart [service]   Restart everything, or one service
  update              Pull latest release, rebuild, auto-rollback on failure
  backup              Dump database + .env + VERSION into a tar.gz
  restore FILE        Restore a backup archive (destructive, asks to confirm)
  set-webhook         Register the Telegram webhook for RUN_MODE=webhook
  delete-webhook      Remove the Telegram webhook (back to polling)
  doctor              Run health diagnostics
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
