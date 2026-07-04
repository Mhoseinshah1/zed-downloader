# Operations & Hardening

Runtime behavior that production operators need to understand: rate limiting, the reliable download queue, ads, editable bot texts, and the security hardening around CORS, Redis, and admin auth. All of these are configured through the single root `.env` (see [`.env.example`](../.env.example)); the installer generates the secrets. Restart after changing env vars: `zed-downloader restart`.

Related: [API.md](API.md) · [PAYMENTS.md](PAYMENTS.md) · [INSTALL.md](INSTALL.md) · [UPDATE.md](UPDATE.md)

---

## Rate limiting

A **fixed-window** throttle on download requests, applied **per Telegram user and, separately, per group chat** so one user cannot flood the queue and one busy group cannot starve everyone else. It runs in `apps/api/app/services/ratelimit.py`, backed by Redis (one `INCR` counter key per identity, expiring after the window).

Checked **before** any real work in `POST /api/internal/download/request`; when either the user or the group is over budget the request is denied with `reason:"rate_limited"` (the bot acknowledges, nothing is queued, no quota is touched).

**Fails open:** if Redis is unreachable the limiter allows the request rather than blocking all downloads — the queue and quota checks remain the real safety nets.

| Env var | Default | Meaning |
|---|---|---|
| `RATE_LIMIT_ENABLED` | `true` | Master switch. `false` disables throttling entirely. |
| `RATE_LIMIT_MAX_REQUESTS` | `5` | Max requests allowed per identity per window. |
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Window length in seconds; the window is anchored to the first request in it. |

---

## Reliable download queue (Redis Streams)

The queue in `apps/api/app/workers/queue.py` uses **Redis Streams with a consumer group**, replacing the earlier at-most-once `BLPOP` list. `BLPOP` loses a job if the worker dies mid-download; Streams keep every delivered-but-unacknowledged job in the group's **Pending Entries List (PEL)** so it can be recovered.

**Keys**

| Name | Value |
|---|---|
| Stream | `zed:download:stream` |
| Consumer group | `zed:workers` |
| Dead-letter stream | `zed:download:dead` |

**Lifecycle of one job**

```
 enqueue                 → XADD to zed:download:stream
 worker picks up new     → XREADGROUP ">"        (never-delivered entries)
 worker reclaims stale   → XAUTOCLAIM            (entries left by a crashed worker)
 success / terminal fail → XACK + XDEL           (stream length = live backlog only)
 worker crashes mid-job  → entry stays in the PEL, reclaimable after the idle window
 too many reclaims       → XADD to zed:download:dead, then XACK + XDEL the original
```

- **Acknowledgement:** a job stays pending until the worker explicitly `XACK`s it on completion (success *or* terminal failure), then it is `XDEL`'d so `XLEN` reflects only outstanding work (this is the "queue length" on the dashboard).
- **Reclaim:** `XAUTOCLAIM` lets a healthy worker take over jobs that have been idle (unacked) longer than `QUEUE_RECLAIM_IDLE_MS`, i.e. jobs orphaned by a crashed worker.
- **Dead-letter:** once a job has been reclaimed more than `QUEUE_MAX_DELIVERIES` times it is moved to `zed:download:dead` (with the original id and a reason) instead of looping forever. Inspect the dead-letter stream to triage jobs that repeatedly fail.
- The consumer group (and the stream) is created idempotently on startup (`XGROUP CREATE ... MKSTREAM`, ignoring `BUSYGROUP`).

| Env var | Default | Meaning |
|---|---|---|
| `QUEUE_MAX_DELIVERIES` | `3` | Reclaim attempts before a job is dead-lettered. |
| `QUEUE_RECLAIM_IDLE_MS` | `600000` | How long (ms) a job must idle unacked before another worker may reclaim it (default 10 min). |

The pipeline is deliberately transparent — plain Redis commands, no Celery — so the whole flow is auditable.

---

## Ads

The worker can send a **weighted-random active ad** around each download. Ads are managed from the panel **Ads** page (`title`, `content`, `media_url`, `is_active`, `weight`) and stored in the `ads` table; only active ads are eligible, and higher `weight` makes an ad more likely to be picked.

| Env var | Default | Meaning |
|---|---|---|
| `ADS_ENABLED` | `true` | Master switch for ad delivery. |
| `ADS_PLACEMENT` | `after` | When to send the ad relative to the file: `before`, `after`, or `both`. |

CRUD endpoints: see [API.md — Ads router](API.md#ads-router).

---

## DB-backed editable bot texts

The bot's user-facing strings are **editable at runtime** from the panel **Bot-texts** page, without a redeploy. The `bot_texts` table (`key`, `lang`, `value`) is the source of truth and **overlays** the shipped i18n defaults:

- **Bot:** on startup it fetches `GET /api/internal/texts` (`{lang: {key: value}}`) and overlays those overrides onto its bundled `fa`/`en` JSON. Any key not overridden falls back to the shipped default.
- **Worker:** resolves per-error messages through a cache of the DB texts, falling back to the shipped defaults when a key has no override.

Edit texts via [API.md — Bot-texts router](API.md#bot-texts-router). A `key`+`lang` pair is unique.

---

## CORS restriction

`CORS_ORIGINS` is the comma-separated allow-list of browser origins for the admin panel. It now **defaults to empty = same-origin only**, which is the secure production posture: in production the panel is served **same-origin** through Caddy, so no cross-origin access is needed.

- Set it to a specific panel origin only for a **split deployment**, or to a dev-server origin like `http://localhost:5173` during development.
- **Never use `*` in production.** Beyond being over-permissive, `*` disables *credentialed* CORS and is only honored as a deliberate, explicit opt-out.
- `ENV` (`production` | `development`) selects the deployment posture; keep it `production` on a real server.

| Env var | Default | Meaning |
|---|---|---|
| `ENV` | `production` | Deployment environment: `production` \| `development`. |
| `CORS_ORIGINS` | *(empty)* | Allowed browser origins (comma-separated). Empty = same-origin only. |

---

## Redis password

Redis is **internal to the compose network** and additionally **password-protected** (defense in depth). The installer generates `REDIS_PASSWORD`; when it is set, `REDIS_URL` **must embed it**:

```bash
# .env
REDIS_PASSWORD=<generated>                       # openssl rand -hex 24
REDIS_URL=redis://:<generated>@redis:6379/0      # password embedded
```

Both the queue and the rate limiter connect through `REDIS_URL`, so keep the two values consistent. If you rotate the password, update both and restart.

---

## Admin token blacklist

Admin JWTs are stateless, so logout is backed by a **revocation list**. Every access and refresh token carries a `jti`; revoked ids are stored in the `revoked_tokens` table and rejected on subsequent requests.

- `POST /api/admin/auth/logout` **revokes the presented access token** and, when the request body includes `{refresh_token}`, **the refresh token too** — so a logged-out session's tokens stop working immediately.
- `POST /api/admin/auth/refresh` rejects a **revoked** refresh token (`401`), so a stolen-then-revoked refresh token cannot mint new access tokens.

No env var — this is always on. See [API.md — Auth router](API.md#auth-router).

---

See also: [API.md](API.md) · [PAYMENTS.md](PAYMENTS.md) · [ADMIN.md](ADMIN.md) · [RELEASING.md](RELEASING.md)
