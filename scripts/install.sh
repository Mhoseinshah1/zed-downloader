#!/usr/bin/env bash
# ==========================================================================
# zed-downloader — one-command installer for Ubuntu servers.
#
# Interactive:
#   sudo bash install.sh
#
# Non-interactive (pre-set any prompt variable to skip its prompt):
#   sudo BOT_TOKEN=... BOT_USERNAME=... OWNER_TELEGRAM_ID=... \
#        DOMAIN=... ACME_EMAIL=... OWNER_ADMIN_EMAIL=... \
#        OWNER_ADMIN_PASSWORD=... bash install.sh
# ==========================================================================
set -euo pipefail

# ------------------------------------------------------------------ helpers
C_GREEN=$'\033[1;32m'
C_YELLOW=$'\033[1;33m'
C_RED=$'\033[1;31m'
C_RESET=$'\033[0m'

log()  { echo "${C_GREEN}[zed]${C_RESET} $*"; }
warn() { echo "${C_YELLOW}[zed] WARN:${C_RESET} $*" >&2; }
err()  { echo "${C_RED}[zed] ERROR:${C_RESET} $*" >&2; }
die()  { err "$*"; exit 1; }

INSTALL_DIR="/opt/zed-downloader"
REPO_URL="${REPO_URL:-https://github.com/mhoseinshah1/zed-downloader.git}"

# prompt_var VAR "question" [default]
# Uses the pre-set environment variable when present (non-interactive
# mode); otherwise asks on the terminal. Empty answers are rejected
# unless a default exists.
prompt_var() {
    local var="$1" question="$2" default="${3:-}" value
    if [[ -n "${!var:-}" ]]; then
        log "$var: provided via environment"
        return 0
    fi
    if [[ ! -t 0 ]]; then
        if [[ -n "$default" ]]; then
            printf -v "$var" '%s' "$default"
            warn "no TTY: using default for $var ($default)"
            return 0
        fi
        die "no TTY and \$$var is not set — export $var for non-interactive install"
    fi
    while true; do
        if [[ -n "$default" ]]; then
            read -rp "  $question [$default]: " value
            value="${value:-$default}"
        else
            read -rp "  $question: " value
        fi
        [[ -n "$value" ]] && break
        echo "  a value is required."
    done
    printf -v "$var" '%s' "$value"
}

# ------------------------------------------------------- root + OS detection
[[ "${EUID}" -eq 0 ]] || die "this installer must run as root (use sudo)."

if [[ -r /etc/os-release ]]; then
    # shellcheck disable=SC1091
    . /etc/os-release
    if [[ "${ID:-}" == "ubuntu" && ( "${VERSION_ID:-}" == "22.04" || "${VERSION_ID:-}" == "24.04" ) ]]; then
        log "detected Ubuntu ${VERSION_ID}"
    else
        warn "untested OS: ${PRETTY_NAME:-unknown} — Ubuntu 22.04/24.04 is recommended. Continuing anyway."
    fi
else
    warn "/etc/os-release not found — cannot detect OS. Continuing anyway."
fi

# --------------------------------------------------------------- base tools
export DEBIAN_FRONTEND=noninteractive

need_pkgs=()
command -v git     >/dev/null 2>&1 || need_pkgs+=(git)
command -v curl    >/dev/null 2>&1 || need_pkgs+=(curl)
command -v openssl >/dev/null 2>&1 || need_pkgs+=(openssl)
if [[ ${#need_pkgs[@]} -gt 0 ]]; then
    log "installing packages: ${need_pkgs[*]}"
    apt-get update -qq
    apt-get install -y -qq "${need_pkgs[@]}" ca-certificates
fi

# --------------------------------------------------------------------- docker
if ! command -v docker >/dev/null 2>&1; then
    log "Docker not found — installing via get.docker.com"
    tmp_script="$(mktemp)"
    curl -fsSL https://get.docker.com -o "$tmp_script"
    sh "$tmp_script"
    rm -f "$tmp_script"
fi

if ! docker compose version >/dev/null 2>&1; then
    log "docker compose plugin missing — trying apt"
    apt-get update -qq
    apt-get install -y -qq docker-compose-plugin || true
fi
docker compose version >/dev/null 2>&1 \
    || die "the 'docker compose' plugin is required but could not be installed."

systemctl enable --now docker >/dev/null 2>&1 || true

# ------------------------------------------------------------- repo location
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)"; then
    APP_DIR="$REPO_ROOT"
    log "running from an existing checkout — installing in place: $APP_DIR"
else
    APP_DIR="$INSTALL_DIR"
    if [[ -d "$APP_DIR/.git" ]]; then
        log "using existing clone at $APP_DIR"
    else
        log "cloning $REPO_URL -> $APP_DIR"
        git clone "$REPO_URL" "$APP_DIR"
    fi
fi

# Keep the canonical path working even for non-standard checkouts, so
# the zed-downloader CLI (default ZED_DIR=/opt/zed-downloader) finds it.
if [[ "$APP_DIR" != "$INSTALL_DIR" && ! -e "$INSTALL_DIR" ]]; then
    ln -s "$APP_DIR" "$INSTALL_DIR"
    log "symlinked $INSTALL_DIR -> $APP_DIR"
fi

cd "$APP_DIR"

# ------------------------------------------------------------------- prompts
log "configuration — answers are written to $APP_DIR/.env"
prompt_var BOT_TOKEN            "Telegram bot token (from @BotFather)"
prompt_var BOT_USERNAME         "Bot username, without @"
prompt_var OWNER_TELEGRAM_ID    "Owner's numeric Telegram ID"
prompt_var DOMAIN               "Public domain pointing at this server (e.g. dl.example.com)"
prompt_var ACME_EMAIL           "E-mail for Let's Encrypt" "admin@${DOMAIN}"
prompt_var OWNER_ADMIN_EMAIL    "Admin panel owner e-mail" "${ACME_EMAIL}"
prompt_var OWNER_ADMIN_PASSWORD "Admin panel owner password"

# ------------------------------------------------------------------- secrets
gen_hex() { openssl rand -hex 32; }

gen_fernet() {
    # A Fernet key is url-safe base64 of 32 random bytes.
    local key=""
    if command -v python3 >/dev/null 2>&1; then
        key="$(python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())' 2>/dev/null || true)"
    fi
    if [[ -z "$key" ]]; then
        # Fallback: openssl base64 translated to the url-safe alphabet.
        key="$(openssl rand -base64 32 | tr '+/' '-_')"
    fi
    printf '%s' "$key"
}

# Secrets must survive re-runs: the postgres volume was initialized with
# the original POSTGRES_PASSWORD and provider keys at rest are encrypted
# with the original Fernet ENCRYPTION_KEY. Read the PRE-EXISTING .env
# now, BEFORE .env.example may be copied over it below — a grep after
# that copy would only see fresh placeholders.
# Precedence: explicit env var > existing .env value > freshly generated.
EXISTING_ENV="$APP_DIR/.env"

# existing_env KEY — print KEY's value from the pre-existing .env.
# Empty values and the "change-me" placeholder count as absent.
existing_env() {
    local value=""
    if [[ -f "$EXISTING_ENV" ]]; then
        value="$(grep -E "^$1=" "$EXISTING_ENV" 2>/dev/null | head -n1 | cut -d= -f2- || true)"
    fi
    [[ "$value" == "change-me" ]] && value=""
    printf '%s' "$value"
}

# preserve_secret VAR — default VAR from the pre-existing .env unless it
# was explicitly provided via the environment.
preserve_secret() {
    local var="$1" existing
    [[ -n "${!var:-}" ]] && return 0   # explicit env var wins
    existing="$(existing_env "$var")"
    if [[ -n "$existing" ]]; then
        printf -v "$var" '%s' "$existing"
        log "$var: preserved from existing .env"
    fi
}

preserve_secret POSTGRES_PASSWORD
preserve_secret JWT_SECRET
preserve_secret TELEGRAM_WEBHOOK_SECRET
preserve_secret ENCRYPTION_KEY
# REDIS_PASSWORD guards the running redis (--requirepass) and is embedded in
# REDIS_URL; a re-run must keep the existing value so the live redis auth and
# the encrypted state that depends on it stay in sync.
preserve_secret REDIS_PASSWORD

POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-$(gen_hex)}"
JWT_SECRET="${JWT_SECRET:-$(gen_hex)}"
TELEGRAM_WEBHOOK_SECRET="${TELEGRAM_WEBHOOK_SECRET:-$(gen_hex)}"
ENCRYPTION_KEY="${ENCRYPTION_KEY:-$(gen_fernet)}"
REDIS_PASSWORD="${REDIS_PASSWORD:-$(openssl rand -hex 24)}"
log "secrets ready (env-provided or preserved values kept, missing ones generated)"

# ---------------------------------------------------------------- write .env
if [[ -f .env ]]; then
    backup=".env.backup.$(date +%Y%m%d-%H%M%S)"
    cp .env "$backup"
    warn "existing .env backed up to $backup — values will be updated in place"
else
    [[ -f .env.example ]] || die ".env.example not found in $APP_DIR"
    cp .env.example .env
fi
chmod 600 .env

# Escape characters special on the sed replacement side (\, & and our
# chosen delimiter |).
sed_escape() { printf '%s' "$1" | sed -e 's/[\\|&]/\\&/g'; }

# set_env KEY VALUE — update KEY in .env, appending it when absent.
set_env() {
    local key="$1" value="$2" esc
    esc="$(sed_escape "$value")"
    if grep -qE "^${key}=" .env; then
        sed -i "s|^${key}=.*|${key}=${esc}|" .env
    else
        echo "${key}=${value}" >> .env
    fi
}

# DATABASE_URL is rebuilt from parts so it always matches the (possibly
# preserved) POSTGRES_PASSWORD above; user/db come from .env defaults.
POSTGRES_USER="$(grep -E '^POSTGRES_USER=' .env | head -n1 | cut -d= -f2- || true)"
POSTGRES_USER="${POSTGRES_USER:-zed}"
POSTGRES_DB="$(grep -E '^POSTGRES_DB=' .env | head -n1 | cut -d= -f2- || true)"
POSTGRES_DB="${POSTGRES_DB:-zed_downloader}"
DATABASE_URL="postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@postgres:5432/${POSTGRES_DB}"

# REDIS_URL embeds the (possibly preserved) REDIS_PASSWORD so api/worker/bot
# authenticate against the password-protected redis. Empty-user form
# redis://:PASSWORD@host is what redis expects for a requirepass-only server.
REDIS_URL="redis://:${REDIS_PASSWORD}@redis:6379/0"

set_env DOMAIN                  "$DOMAIN"
set_env ACME_EMAIL              "$ACME_EMAIL"
set_env POSTGRES_USER           "$POSTGRES_USER"
set_env POSTGRES_DB             "$POSTGRES_DB"
set_env POSTGRES_PASSWORD       "$POSTGRES_PASSWORD"
set_env DATABASE_URL            "$DATABASE_URL"
set_env REDIS_PASSWORD          "$REDIS_PASSWORD"
set_env REDIS_URL               "$REDIS_URL"
set_env JWT_SECRET              "$JWT_SECRET"
set_env ENCRYPTION_KEY          "$ENCRYPTION_KEY"
set_env TELEGRAM_WEBHOOK_SECRET "$TELEGRAM_WEBHOOK_SECRET"
set_env BOT_TOKEN               "$BOT_TOKEN"
set_env BOT_USERNAME            "$BOT_USERNAME"
set_env OWNER_ADMIN_EMAIL       "$OWNER_ADMIN_EMAIL"
set_env OWNER_ADMIN_PASSWORD    "$OWNER_ADMIN_PASSWORD"
set_env OWNER_TELEGRAM_ID       "$OWNER_TELEGRAM_ID"
# NOTE: only used when RUN_MODE=webhook; harmless in the default polling mode.
set_env WEBHOOK_BASE_URL        "https://${DOMAIN}"
# Production defaults: the admin panel is served same-origin behind Caddy, so
# CORS must stay EMPTY (same-origin only). Forced here so a re-run over an
# older .env that lacked these — or had them loosened — lands on the secure
# values.
set_env ENV                     "production"
set_env CORS_ORIGINS            ""
# Real app version from the repo VERSION file (baked into the image + reported
# by /health and /ready).
set_env APP_VERSION             "$(cat "$APP_DIR/VERSION" 2>/dev/null || echo 1.0.0)"
log ".env written"

# ------------------------------------------------------------ CLI installer
cp "$APP_DIR/scripts/manage.sh" /usr/local/bin/zed-downloader
chmod +x /usr/local/bin/zed-downloader
log "management CLI installed: zed-downloader (try: zed-downloader help)"

# -------------------------------------------------------------- build + run
# Same compose invocation manage.sh uses. NOTE: --env-file (not
# --project-directory) so ${VAR} interpolation reads the root .env while
# relative paths inside the compose file stay anchored to deploy/.
COMPOSE=(docker compose -f "$APP_DIR/deploy/docker-compose.yml" --env-file "$APP_DIR/.env")

# ------------------------------------------------------------- preflight
# Catch broken files / config BEFORE spending minutes on a build that can only
# fail. Every check is fatal (die) with a specific message.
preflight() {
    log "preflight checks..."

    for f in deploy/docker-compose.yml apps/api/entrypoint.sh apps/api/Dockerfile \
             apps/api/requirements.txt apps/bot/requirements.txt VERSION .env; do
        [[ -f "$APP_DIR/$f" ]] || die "preflight: required file missing: $f"
    done

    # Shell scripts must parse.
    for s in "$APP_DIR"/scripts/*.sh "$APP_DIR/apps/api/entrypoint.sh"; do
        bash -n "$s" || die "preflight: shell syntax error in $s"
    done

    # .env must carry the settings the API needs to even import its config.
    for key in DATABASE_URL REDIS_URL JWT_SECRET POSTGRES_PASSWORD; do
        val="$(grep "^${key}=" "$APP_DIR/.env" | cut -d= -f2-)"
        [[ -n "$val" && "$val" != "change-me" ]] || die "preflight: .env is missing a real value for ${key}"
    done

    # The password inside DATABASE_URL must match POSTGRES_PASSWORD, or the API
    # can never authenticate (the classic 120s-timeout failure).
    local pg_pw db_pw
    pg_pw="$(grep '^POSTGRES_PASSWORD=' "$APP_DIR/.env" | cut -d= -f2-)"
    db_pw="$(grep '^DATABASE_URL=' "$APP_DIR/.env" | sed -n 's#.*://[^:]*:\([^@]*\)@.*#\1#p')"
    [[ "$pg_pw" == "$db_pw" ]] || die "preflight: POSTGRES_PASSWORD does not match the password in DATABASE_URL"

    # Compose file must be valid with this .env.
    "${COMPOSE[@]}" config >/dev/null 2>&1 || die "preflight: 'docker compose config' failed — run it manually to see why"

    log "preflight OK"
}
preflight

log "building and starting the stack (first build can take several minutes)"
"${COMPOSE[@]}" up -d --build

# NOTE: the API port is not published on the host, so the health probe
# runs inside the api container (curl http://localhost:8000/health).
log "waiting for the API to become healthy (up to ~180s)"
healthy=0
for _ in $(seq 1 90); do
    if "${COMPOSE[@]}" exec -T api curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        healthy=1
        break
    fi
    sleep 2
done

if [[ "$healthy" -ne 1 ]]; then
    err "API did not become healthy in time. Dumping diagnostics — do not panic, the"
    err "cause is almost always printed in the api logs below."
    echo "------------------------------------------------------------------ containers"
    docker ps -a --filter "name=zed_" 2>/dev/null || docker ps -a
    echo "------------------------------------------------------- zed_api health state"
    docker inspect zed_api --format '{{json .State.Health}}' 2>/dev/null || true
    echo "----------------------------------------------------- zed_api logs (tail 200)"
    docker logs zed_api --tail=200 2>&1 || "${COMPOSE[@]}" logs --tail=200 api 2>&1 || true
    echo "----------------------------------------------------- zed_bot logs (tail 100)"
    docker logs zed_bot --tail=100 2>&1 || "${COMPOSE[@]}" logs --tail=100 bot 2>&1 || true
    echo "---------------------------------------------------- zed_worker logs (tail 100)"
    docker logs zed_worker --tail=100 2>&1 || "${COMPOSE[@]}" logs --tail=100 worker 2>&1 || true
    echo "----------------------------------------------------------------------------"
    if docker logs zed_api 2>&1 | grep -q "28P01\|password authentication failed\|initialized with a DIFFERENT password"; then
        err "ROOT CAUSE: the API cannot authenticate to Postgres. The postgres data"
        err "volume was initialized with a different password than the current .env."
        err "FIX (this DELETES database data): zed-downloader reset-db   then re-run install."
    fi
    err "More: zed-downloader logs api   |   zed-downloader status"
    exit 1
fi

# Health (liveness) passed. Also probe readiness (DB + Redis) — informational:
# real traffic is served once this is ready, but a transient not-ready here does
# not fail the install (dependencies may still be warming up).
if "${COMPOSE[@]}" exec -T api curl -fsS http://localhost:8000/ready >/dev/null 2>&1; then
    log "API readiness (/ready): OK — database and Redis reachable"
else
    err "API is healthy but /ready is not OK yet (database or Redis still warming up)."
    err "Check shortly with: zed-downloader status"
fi

# ------------------------------------------------------------------ summary
VERSION_STR="$(cat "$APP_DIR/VERSION" 2>/dev/null || echo unknown)"
cat <<EOF

${C_GREEN}==============================================================
  zed-downloader v${VERSION_STR} installed successfully
==============================================================${C_RESET}
  Admin panel : https://${DOMAIN}
  Admin login : ${OWNER_ADMIN_EMAIL}
  Telegram bot: https://t.me/${BOT_USERNAME}
  Install dir : ${APP_DIR}
  CLI         : zed-downloader {status|logs|update|backup|doctor|...}
  Update later: zed-downloader update
                (backup -> pull -> rebuild -> health gate -> auto-rollback)

  Webhook mode (optional, default is polling):
    zed-downloader set-webhook   # then set RUN_MODE=webhook in .env
${C_GREEN}==============================================================${C_RESET}
EOF
