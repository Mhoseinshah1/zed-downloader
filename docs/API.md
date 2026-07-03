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
| POST | `/api/admin/auth/refresh` | public | `{refresh_token}` | `{access_token, refresh_token, token_type}` |
| POST | `/api/admin/auth/logout` | admin JWT | — | `{ok: true}` |
| GET | `/api/admin/me` | admin JWT | — | current admin `{id, email, full_name, role}` (see code) |

## Internal router (bot → API)

All routes require the `X-Internal-Secret` header.

| Method | Path | Body / Query | Response |
|---|---|---|---|
| POST | `/api/internal/users/upsert` | `{telegram_id:int, username?, first_name?, last_name?, language?}` | `{id, telegram_id, language, is_blocked}` |
| POST | `/api/internal/users/{telegram_id}/language` | `{language:str}` | `{ok: true}` |
| POST | `/api/internal/groups/upsert` | `{telegram_chat_id:int, title?, username?}` | `{id, telegram_chat_id, is_enabled}` |
| POST | `/api/internal/download/request` | `{telegram_id:int, chat_id?:int\|null, url:str, username?, first_name?, last_name?, language?}` — `chat_id` is the group chat id when called from a group, null/omitted in private chat | see below |
| GET | `/api/internal/plans` | — | `{plans:[{id, name, price, currency, duration_days, download_limit}]}` |
| GET | `/api/internal/forced-join` | — | `{channels:[{id, channel_id?:int, username:str, title?:str}]}` |
| POST | `/api/internal/payments/create` | `{telegram_id:int, plan_id:int, gateway:"zarinpal"}` | `{payment_id:int, payment_url:str, authority:str}` |

**`POST /api/internal/download/request` responses**

| Case | Shape |
|---|---|
| accepted | `{status:"queued", request_id:int}` |
| denied | `{status:"denied", reason:"blocked"\|"maintenance"\|"limit_reached"\|"need_subscription"\|"group_disabled", plans?:[{id, name, price, currency, duration_days, download_limit}]}` — `plans` accompanies subscription-related denials |
| bad URL | `{status:"error", reason:"unsupported_url"}` |

The bot only acknowledges (queued / denied / buy prompt). The **worker** delivers the actual file — or a localized per-error message (see [PROVIDERS.md](PROVIDERS.md)) — directly to the Telegram chat.

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
| GET | `/api/admin/providers` | admin JWT | — | list of providers; API keys are never returned in plaintext (see code) |
| POST | `/api/admin/providers` | admin JWT | provider fields: name, provider_type (registry key), platform_id, priority, api_key, base_url, timeout, settings, is_active (see code) | created provider |
| PATCH | `/api/admin/providers/{id}` | admin JWT | partial provider fields (see code) | updated provider |
| DELETE | `/api/admin/providers/{id}` | admin JWT | — | `{ok:true}` (see code) |
| POST | `/api/admin/providers/{id}/test` | admin JWT | — | health-check result (see code) |
| GET | `/api/admin/providers/{id}/balance` | admin JWT | — | upstream balance, `{"supported": false}` when the provider has none (see code) |

`provider_type` must be a key of `REGISTRY` in `apps/api/app/providers/manager.py` — see [PROVIDERS.md](PROVIDERS.md).

## Payments router

| Method | Path | Auth | Body / Query | Response |
|---|---|---|---|---|
| GET | `/api/admin/plans` | admin JWT | — | list of plans (see code) |
| POST | `/api/admin/plans` | admin JWT | plan fields: name, price, currency, duration_days, download_limit, scope, is_active (see code) | created plan |
| PATCH | `/api/admin/plans/{id}` | admin JWT | partial plan fields (see code) | updated plan |
| DELETE | `/api/admin/plans/{id}` | admin JWT | — | `{ok:true}` (see code) |
| GET | `/api/admin/payments` | admin JWT | pagination/filter query (see code) | list of payments (see code) |
| GET | `/payments/zarinpal/callback` | **public** | query: `Authority=`, `Status=` (set by Zarinpal's redirect) | HTML result page shown to the paying user |

The callback is idempotent and safe against replays — see the money-safety invariants in [PAYMENTS.md](PAYMENTS.md).

## Misc

| Method | Path | Auth | Response |
|---|---|---|---|
| GET | `/health` | public | service health/version (see code) — used by the installer, the updater's post-update check, and uptime monitors |

---

Shapes marked "(see code)" are implemented in `apps/api/app/routes/` and may carry extra fields; everything else is the stable contract consumed by the bot (`apps/bot`) and the panel (`apps/admin`). Do not build against undocumented fields.

See also: [ADMIN.md](ADMIN.md) · [PROVIDERS.md](PROVIDERS.md) · [PAYMENTS.md](PAYMENTS.md)
