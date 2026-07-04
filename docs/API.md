# API Reference

All routes are served by the FastAPI backend (`apps/api`, port 8000) and exposed publicly through Caddy at `https://DOMAIN`.

**Auth modes**

| Mode | How |
|---|---|
| admin JWT | `Authorization: Bearer <access_token>` — obtained from `POST /api/admin/auth/login`; short-lived (TTL `JWT_ACCESS_TTL_MINUTES`), refresh with the refresh token (TTL `JWT_REFRESH_TTL_DAYS`) |
| X-Internal-Secret | `X-Internal-Secret: <TELEGRAM_WEBHOOK_SECRET>` header — bot→API calls only; never expose this secret |
| public | No auth |

Errors follow FastAPI conventions: `401` for missing/invalid credentials, `403` for insufficient role, `404` for missing resources, `422` for validation errors (see code).

---

## Auth router

| Method | Path | Auth | Body | Response |
|---|---|---|---|---|
| POST | `/api/admin/auth/login` | public | `{email, password}` | `{access_token, refresh_token, token_type, admin:{id, email, full_name, role}}` |
| POST | `/api/admin/auth/refresh` | public | `{refresh_token}` | `{access_token, refresh_token, token_type}` — a **revoked** refresh token is rejected `401` |
| POST | `/api/admin/auth/logout` | admin JWT | `{refresh_token?}` (optional) | `{ok: true}` — **revokes** the presented access token and, when the body is supplied, the refresh token; both stop working immediately (see [OPERATIONS.md — Admin token blacklist](OPERATIONS.md#admin-token-blacklist)) |
| GET | `/api/admin/me` | admin JWT | — | current admin `{id, email, full_name, role}` (see code) |

Every JWT carries a `jti`; revoked token ids live in the `revoked_tokens` table and are rejected on both normal requests and refresh.

## Internal router (bot → API)

All routes require the `X-Internal-Secret` header.

| Method | Path | Body / Query | Response |
|---|---|---|---|
| POST | `/api/internal/users/upsert` | `{telegram_id:int, username?, first_name?, last_name?, language?}` | `{id, telegram_id, language, is_blocked}` |
| POST | `/api/internal/users/{telegram_id}/language` | `{language:str}` | `{ok: true}` |
| POST | `/api/internal/groups/upsert` | `{telegram_chat_id:int, title?, username?}` | `{id, telegram_chat_id, is_enabled}` |
| POST | `/api/internal/download/request` | `{telegram_id:int, chat_id?:int\|null, url:str, username?, first_name?, last_name?, language?}` — `chat_id` is the group chat id when called from a group, null/omitted in private chat | see below |
| GET | `/api/internal/plans` | query: `scope=user` (default) `\| group` | `{plans:[{id, name, price, currency, duration_days, download_limit}]}` — active plans for the scope; `scope=group` lists group-buyable plans |
| GET | `/api/internal/texts` | — | `{texts:{<lang>:{<key>:<value>}}}` — all panel-editable bot texts; the bot overlays these onto its bundled i18n (see [OPERATIONS.md — Editable bot texts](OPERATIONS.md#db-backed-editable-bot-texts)) |
| GET | `/api/internal/forced-join` | — | `{channels:[{id, channel_id?:int, username:str, title?:str}]}` |
| POST | `/api/internal/payments/create` | `{telegram_id:int, plan_id:int, gateway:"zarinpal", chat_id?:int\|null}` — `chat_id` is **required for group-scope plans** (the negative group chat id the subscription binds to); it must be omitted/null for user plans | `{payment_id:int, payment_url:str, authority:str}` |

**`POST /api/internal/download/request` responses**

| Case | Shape |
|---|---|
| accepted | `{status:"queued", request_id:int}` |
| denied | `{status:"denied", reason:"blocked"\|"maintenance"\|"limit_reached"\|"need_subscription"\|"group_disabled"\|"rate_limited", plans?:[{id, name, price, currency, duration_days, download_limit}]}` — `plans` accompanies subscription-related denials |
| bad URL | `{status:"error", reason:"unsupported_url"}` |
| queue down | `{status:"error", reason:"queue_unavailable"}` |

The bot only acknowledges (queued / denied / buy prompt). The **worker** delivers the actual file — or a localized per-error message (see [PROVIDERS.md](PROVIDERS.md)) — directly to the Telegram chat, and (when enabled) an ad before/after it.

The request is throttled **before** any real work: a per-user and per-group-chat fixed-window limiter can short-circuit with `reason:"rate_limited"` — see [OPERATIONS.md — Rate limiting](OPERATIONS.md#rate-limiting).

## Dashboard router

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/api/admin/dashboard/stats` | admin JWT | `{users_total, users_today, downloads_total, downloads_today, active_subscriptions, revenue_total, revenue_today, queue_length, downloads_by_status}` |
| GET | `/api/admin/system/health` | admin JWT | `{api:"ok", database:"ok"\|"error", redis:"ok"\|"error", version}` |

## Users router

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| GET | `/api/admin/users` | admin JWT | query: `search=`, `page=1`, `page_size=20` | `{items:[user...], total, page, page_size}` |
| GET | `/api/admin/users/{id}` | admin JWT | — | user object |
| PATCH | `/api/admin/users/{id}` | admin JWT | partial user fields (see code) | updated user object |
| POST | `/api/admin/users/{id}/block` | admin JWT | — | updated user / `{ok:true}` (see code) |
| POST | `/api/admin/users/{id}/unblock` | admin JWT | — | updated user / `{ok:true}` (see code) |
| GET | `/api/admin/groups` | admin JWT | pagination query (see code) | list of groups (see code) |
| PATCH | `/api/admin/groups/{id}` | admin JWT | partial group fields, e.g. `is_enabled` (see code) | updated group (see code) |

**user object:** `{id, telegram_id, username, first_name, last_name, language, is_blocked, total_downloads, created_at}`

## Catalog router (platforms & providers)

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| GET | `/api/admin/platforms` | admin JWT | — | list of platforms (see code) |
| POST | `/api/admin/platforms` | admin JWT | platform fields: name, url_regex, is_active, sort_order (see code) | created platform |
| PATCH | `/api/admin/platforms/{id}` | admin JWT | partial platform fields (see code) | updated platform |
| DELETE | `/api/admin/platforms/{id}` | admin JWT | — | `{ok:true}` (see code) |
| GET | `/api/admin/providers` | admin JWT | — | list of providers; **the API key is write-only** — it is never returned, responses carry only a `has_api_key` boolean (see code) |
| POST | `/api/admin/providers` | admin JWT | provider fields: name, provider_type (registry key), platform_id, priority, api_key, base_url, timeout, settings, is_active (see code) | created provider (write-only `api_key`, response has `has_api_key`) |
| PATCH | `/api/admin/providers/{id}` | admin JWT | partial provider fields (see code) | updated provider |
| DELETE | `/api/admin/providers/{id}` | admin JWT | — | `{ok:true}` (see code) |
| POST | `/api/admin/providers/{id}/test` | admin JWT | — | health-check result (see code) |
| GET | `/api/admin/providers/{id}/balance` | admin JWT | — | upstream balance, `{"supported": false}` when the provider has none (see code) |

`provider_type` must be a key of `REGISTRY` in `apps/api/app/providers/manager.py` — see [PROVIDERS.md](PROVIDERS.md). Provider **API keys are write-only**: send `api_key` on create/patch (Fernet-encrypted at rest), but no endpoint ever returns it — only `has_api_key`. On PATCH, omitting `api_key` leaves the stored key unchanged and sending `""` clears it.

## Payments router

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| GET | `/api/admin/plans` | admin JWT | — | list of plans (see code) |
| POST | `/api/admin/plans` | admin JWT | plan fields: name, price, currency, duration_days, download_limit, scope (`user`\|`group`), is_active (see code) | created plan |
| PATCH | `/api/admin/plans/{id}` | admin JWT | partial plan fields (see code) | updated plan |
| DELETE | `/api/admin/plans/{id}` | admin JWT | — | `{ok:true}` (see code) |
| GET | `/api/admin/payments` | admin JWT | pagination/filter query (see code) | list of payments (see code) |
| GET | `/payments/zarinpal/callback` | **public** | query: `Authority=`, `Status=` (set by Zarinpal's redirect) | HTML result page shown to the paying user |

The callback is idempotent and safe against replays — see the money-safety invariants in [PAYMENTS.md](PAYMENTS.md). A plan's `scope` (`user` vs `group`) decides who the resulting subscription binds to; group plans are bought from inside the group via `/api/internal/payments/create` with `chat_id` — see [PAYMENTS.md — Group subscription purchase](PAYMENTS.md#group-subscription-purchase).

## Settings router

Key/value operational settings (`super_admin`). Unknown keys may be pre-staged with `PUT` so operators can set values the code reads with a default.

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| GET | `/api/admin/settings` | admin JWT | — | `{items:[{key, value, description}]}` |
| GET | `/api/admin/settings/{key}` | admin JWT | — | `{key, value, description}` (`404` if absent) |
| PUT | `/api/admin/settings/{key}` | admin JWT | `{value}` | upserted `{key, value, description}` |

## Ads router

Weighted-random promotional messages the worker sends around downloads (`super_admin`, `content_manager`). See [OPERATIONS.md — Ads](OPERATIONS.md#ads).

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| GET | `/api/admin/ads` | admin JWT | — | `{items:[{id, title, content, media_url, is_active, weight, created_at}]}` |
| POST | `/api/admin/ads` | admin JWT | `{title, content, media_url?, is_active?, weight?}` | created ad |
| PATCH | `/api/admin/ads/{id}` | admin JWT | partial ad fields | updated ad |
| DELETE | `/api/admin/ads/{id}` | admin JWT | — | `{ok:true}` |

## Forced-join router

CRUD for channels a user must join before downloading (`super_admin`, `content_manager`). The bot reads the active set from `GET /api/internal/forced-join`.

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| GET | `/api/admin/forced-join` | admin JWT | — | `{items:[{id, channel_id?, username, title?, is_active, sort_order}]}` |
| POST | `/api/admin/forced-join` | admin JWT | `{username, channel_id?, title?, is_active?, sort_order?}` — a leading `@` on `username` is stripped | created channel |
| PATCH | `/api/admin/forced-join/{id}` | admin JWT | partial fields | updated channel |
| DELETE | `/api/admin/forced-join/{id}` | admin JWT | — | `{ok:true}` |

## Bot-texts router

DB-backed overrides for the bot's per-message strings (`super_admin`, `content_manager`). These overlay the shipped i18n; the bot fetches them via `GET /api/internal/texts`. See [OPERATIONS.md — Editable bot texts](OPERATIONS.md#db-backed-editable-bot-texts).

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| GET | `/api/admin/bot-texts` | admin JWT | query: `lang=` (optional filter) | `{items:[{id, key, lang, value}]}` |
| POST | `/api/admin/bot-texts` | admin JWT | `{key, lang, value}` | created text (`400` if the `key`+`lang` pair already exists) |
| PATCH | `/api/admin/bot-texts/{id}` | admin JWT | `{value}` | updated text |
| DELETE | `/api/admin/bot-texts/{id}` | admin JWT | — | `{ok:true}` |

## Downloads router

Read-only download-request history (`super_admin`, `support`).

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| GET | `/api/admin/downloads` | admin JWT | query: `status=`, `user_id=`, `page=1`, `page_size=20` | `{items:[download...], total, page, page_size}` |
| GET | `/api/admin/downloads/{id}` | admin JWT | — | download object (`404` if absent) |

**download object:** `{id, user_id, group_id, url, platform_id, provider_id, status, error_code, file_name, file_size, file_type, consumed_from, created_at, completed_at}`

## Misc

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/health` | public | service health/version (see code) — used by the installer, the updater's post-update check, and uptime monitors |

---

Shapes marked "(see code)" are implemented in `apps/api/app/routes/` and may carry extra fields; everything else is the stable contract consumed by the bot (`apps/bot`) and the panel (`apps/admin`). Do not build against undocumented fields.

See also: [ADMIN.md](ADMIN.md) · [PROVIDERS.md](PROVIDERS.md) · [PAYMENTS.md](PAYMENTS.md) · [OPERATIONS.md](OPERATIONS.md)
