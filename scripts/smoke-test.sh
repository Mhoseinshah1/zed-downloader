#!/usr/bin/env bash
# ==========================================================================
# zed-downloader — local smoke test.
#
# Brings the stack up from a WORKING .env and proves the API becomes healthy:
#   docker exec zed_api curl -f http://localhost:8000/health   must return JSON.
#
# Safe to run locally: if no .env exists it creates one from .env.example
# (whose defaults are self-consistent — POSTGRES_PASSWORD matches DATABASE_URL,
# no real Telegram token required for the health check) and generates a valid
# ENCRYPTION_KEY. Run from anywhere; paths resolve to the repo root.
#
# Usage:   bash scripts/smoke-test.sh            # keep containers running
#          KEEP=0 bash scripts/smoke-test.sh     # tear down at the end
# ==========================================================================
set -euo pipefail

C_GREEN=$'\033[1;32m'; C_RED=$'\033[1;31m'; C_YEL=$'\033[1;33m'; C_RST=$'\033[0m'
log()  { echo "${C_GREEN}[smoke]${C_RST} $*"; }
warn() { echo "${C_YEL}[smoke] WARN:${C_RST} $*" >&2; }
die()  { echo "${C_RED}[smoke] ERROR:${C_RST} $*" >&2; exit 1; }

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
COMPOSE_FILE="deploy/docker-compose.yml"
ENV_FILE=".env"

command -v docker >/dev/null 2>&1 || die "docker is not installed"
docker compose version >/dev/null 2>&1 || die "the docker compose plugin is required"

# ---- ensure a usable .env ------------------------------------------------
if [[ ! -f "$ENV_FILE" ]]; then
    log "no .env found — creating one from .env.example for the smoke test"
    cp .env.example "$ENV_FILE"
    # A valid Fernet key (only needed once the panel stores provider secrets,
    # but keep .env realistic). Falls back to url-safe base64 of 32 bytes.
    key="$(python3 -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())' 2>/dev/null \
           || openssl rand -base64 32 | tr '+/' '-_')"
    # portable in-place edit
    tmp="$(mktemp)"; sed "s|^ENCRYPTION_KEY=.*|ENCRYPTION_KEY=${key}|" "$ENV_FILE" > "$tmp" && mv "$tmp" "$ENV_FILE"
    warn ".env created with example defaults (POSTGRES_PASSWORD=change-me). Fine for a smoke test; NOT for production."
fi

COMPOSE=(docker compose -f "$COMPOSE_FILE" --env-file "$ENV_FILE")

log "1/4  docker compose config"
"${COMPOSE[@]}" config >/dev/null || die "compose config failed"

log "2/4  docker compose up -d --build (first build can take a few minutes)"
"${COMPOSE[@]}" up -d --build

log "3/4  waiting for the API /health (up to ~180s)"
healthy=0
for _ in $(seq 1 90); do
    if docker exec zed_api curl -fsS http://localhost:8000/health >/dev/null 2>&1; then
        healthy=1; break
    fi
    sleep 2
done

if [[ "$healthy" -ne 1 ]]; then
    echo "----- docker ps -a -----";                docker ps -a --filter name=zed_ || true
    echo "----- zed_api health -----";              docker inspect zed_api --format '{{json .State.Health}}' 2>/dev/null || true
    echo "----- zed_api logs (tail 100) -----";     docker logs zed_api --tail=100 2>&1 || true
    die "API did not become healthy"
fi

log "4/4  /health response:"
docker exec zed_api curl -fsS http://localhost:8000/health
echo
docker logs zed_api --tail=20 2>&1 || true

log "SMOKE TEST PASSED — API is healthy."

if [[ "${KEEP:-1}" == "0" ]]; then
    log "KEEP=0 — tearing down"
    "${COMPOSE[@]}" down
fi
