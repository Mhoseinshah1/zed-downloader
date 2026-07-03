# Installation

This guide takes a fresh Ubuntu server to a fully running zed-downloader stack (bot + API + worker + admin panel) behind Caddy with automatic HTTPS.

> **Legal notice:** this platform downloads **public, permitted content only**. See the legal notice in the [README](../README.md).

## Requirements

| Requirement | Detail |
|---|---|
| OS | Ubuntu 22.04 or 24.04 (x86_64), root/sudo access |
| RAM | 2 GB minimum (4 GB recommended for heavy video workloads) |
| Disk | 10 GB+ free (downloads are temporary, but builds and backups need room) |
| Domain | A domain (or subdomain) with an **A record** pointing at the server's public IP |
| Ports | 80 and 443 free and reachable from the internet (Caddy needs both for Let's Encrypt) |
| Telegram bot | A bot token from [@BotFather](https://t.me/BotFather) (`/newbot`) |

Docker and Docker Compose are installed automatically by the installer if missing.

## Step 1 — DNS

Create an A record for your domain pointing at the server:

```
downloader.example.com.  A  203.0.113.10
```

Verify propagation **before** installing (Let's Encrypt issuance fails otherwise):

```bash
dig +short downloader.example.com
# must print your server's public IP
```

## Step 2 — Run the installer

```bash
git clone https://github.com/mhoseinshah1/zed-downloader.git /opt/zed-downloader
cd /opt/zed-downloader
sudo bash scripts/install.sh
```

## Step 3 — Installer prompts explained

| Prompt | Env var | Notes |
|---|---|---|
| Domain | `DOMAIN` | e.g. `downloader.example.com` — must already resolve to this server |
| ACME e-mail | `ACME_EMAIL` | Used for the Let's Encrypt account (expiry notices) |
| Bot token | `BOT_TOKEN` | From @BotFather, format `123456:AA...` |
| Bot username | `BOT_USERNAME` | Without `@` |
| Run mode | `RUN_MODE` | `polling` (default, zero extra setup) or `webhook` (see below) |
| Owner admin e-mail | `OWNER_ADMIN_EMAIL` | Login for the admin panel; the owner admin is seeded on first API start |
| Owner admin password | `OWNER_ADMIN_PASSWORD` | Change it after first login if you let the installer generate it |
| Owner Telegram ID | `OWNER_TELEGRAM_ID` | Your numeric Telegram user ID |
| Zarinpal merchant ID | `ZARINPAL_MERCHANT_ID` | Optional — leave empty to configure payments later (see [PAYMENTS.md](PAYMENTS.md)) |

## Step 4 — What gets generated

The installer copies `.env.example` to a single root `.env` (consumed by every container via `env_file`) and **generates these secrets for you** — you never type them:

| Env var | Purpose |
|---|---|
| `POSTGRES_PASSWORD` | Database password (also baked into `DATABASE_URL`) |
| `JWT_SECRET` | Signs admin-panel access/refresh tokens |
| `ENCRYPTION_KEY` | Fernet key that encrypts provider API keys at rest |
| `TELEGRAM_WEBHOOK_SECRET` | Doubles as the Telegram webhook `secret_token` **and** the `X-Internal-Secret` header for bot→API calls |

Keep `.env` private and back it up — `ENCRYPTION_KEY` in particular cannot be regenerated without re-entering every provider API key. The full variable reference lives in [`.env.example`](../.env.example).

The installer then builds the images, starts the stack (`postgres`, `redis`, `api`, `worker`, `bot`, `admin`, `caddy`), and installs the `zed-downloader` CLI. On first start the API container runs Alembic migrations and seeds the owner admin and default data.

## Step 5 — Verify

```bash
# 1. All containers running + healthy
zed-downloader status

# 2. API health endpoint (public)
curl -fsS https://downloader.example.com/health

# 3. Bot responds
#    Open Telegram, send /start to your bot.

# 4. Panel login
#    Open https://downloader.example.com in a browser and sign in with
#    OWNER_ADMIN_EMAIL / OWNER_ADMIN_PASSWORD.
```

If all four work, send a public video URL to the bot to test the full download path.

## Webhook vs polling

| | `RUN_MODE=polling` (default) | `RUN_MODE=webhook` |
|---|---|---|
| Setup | None — works everywhere | Requires public HTTPS (`WEBHOOK_BASE_URL`) |
| Latency | Slightly higher | Lower, push-based |
| How it runs | Bot long-polls Telegram | Telegram POSTs updates to the bot's webhook server on port `WEBHOOK_PORT` (8080), routed through Caddy |

To switch to webhook mode:

```bash
# 1. Edit /opt/zed-downloader/.env:
#      RUN_MODE=webhook
#      WEBHOOK_BASE_URL=https://downloader.example.com
# 2. Restart and register the webhook with Telegram:
zed-downloader restart
zed-downloader set-webhook
```

`set-webhook` calls Telegram's `setWebhook` with `TELEGRAM_WEBHOOK_SECRET` as the `secret_token`, so the bot rejects forged webhook calls. To go back, set `RUN_MODE=polling` and restart — the bot deletes the webhook itself when polling starts.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Caddy exits immediately; `zed-downloader logs caddy` shows "address already in use" | Port 80/443 already taken (apache2/nginx on the host) | `sudo systemctl disable --now apache2 nginx`, then `zed-downloader restart` |
| HTTPS certificate errors / ACME challenge failures | DNS not propagated, or A record points elsewhere | `dig +short $DOMAIN` must return this server's IP; wait for propagation and restart Caddy |
| `docker compose` fails to start / `Cannot connect to the Docker daemon` | Docker service not running | `sudo systemctl enable --now docker`, then re-run the installer or `zed-downloader start` |
| Bot logs show `401 Unauthorized` from api.telegram.org | Wrong `BOT_TOKEN` | Re-check the token from @BotFather in `.env`, then `zed-downloader restart` |
| Bot replies "queued" but no file arrives | Worker down or provider failing | `zed-downloader logs worker`; check provider status in the panel (see [PROVIDERS.md](PROVIDERS.md)) |
| Panel loads but login fails | Owner admin not seeded yet / wrong credentials | `zed-downloader logs api` for seed errors; credentials come from `OWNER_ADMIN_EMAIL/PASSWORD` in `.env` |
| Files over ~50 MB fail to send | Standard Telegram Bot API upload cap | Lower `MAX_FILE_SIZE_MB` to `50`, or wait for the self-hosted telegram-bot-api option (v2) |

Next steps: [UPDATE.md](UPDATE.md) for updates and backups · [ADMIN.md](ADMIN.md) for the panel · [PAYMENTS.md](PAYMENTS.md) to enable payments.
