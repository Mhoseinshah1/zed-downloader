#!/usr/bin/env bash
# ==========================================================================
# zed-downloader — remote one-liner updater.
#
# Ensures the repo exists at the install dir (clones if missing) and hands off
# to the real updater (scripts/update.sh), which handles the self-update
# re-exec, backup, health gate and rollback.
#
# Usage:
#   bash <(curl -fsSL https://raw.githubusercontent.com/Mhoseinshah1/zed-downloader/main/scripts/remote-update.sh)
#
# Env: ZED_DIR (install dir, default /opt/zed-downloader), REPO_URL.
# ==========================================================================
set -euo pipefail

APP_DIR="${ZED_DIR:-/opt/zed-downloader}"
REPO_URL="${REPO_URL:-https://github.com/Mhoseinshah1/zed-downloader.git}"

if [[ ! -d "$APP_DIR/.git" ]]; then
    echo "[zed] $APP_DIR is not a checkout — cloning $REPO_URL"
    git clone "$REPO_URL" "$APP_DIR"
fi

exec bash "$APP_DIR/scripts/update.sh"
