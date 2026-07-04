# Admin Panel Guide

The admin panel is a React 18 + Vite app (`apps/admin`) served by nginx and exposed through Caddy at `https://DOMAIN`. It consumes the admin API documented in [API.md](API.md).

## Login

- Open `https://DOMAIN` and sign in with e-mail + password.
- The **owner admin** account is created automatically by the installer on first API start, from the `OWNER_ADMIN_EMAIL` / `OWNER_ADMIN_PASSWORD` values in `.env` (see [INSTALL.md](INSTALL.md)).
- Sessions use short-lived JWT access tokens (`JWT_ACCESS_TTL_MINUTES`, default 30) that the panel refreshes automatically with the refresh token (`JWT_REFRESH_TTL_DAYS`, default 7). Logout **revokes both** the access and refresh tokens so they stop working immediately — see [OPERATIONS.md — Admin token blacklist](OPERATIONS.md#admin-token-blacklist).
- If you forget the owner password: change `OWNER_ADMIN_PASSWORD` in `.env` and restart — the seeder targets the owner account. <!-- NOTE: behavior of re-seeding an existing owner is implementation-defined; see the API seeder code. -->

## Dashboard

The dashboard (data from `GET /api/admin/dashboard/stats`) shows stat cards:

| Card | Meaning |
|---|---|
| Users total / today | Registered bot users, and how many joined today |
| Downloads total / today | Download requests processed |
| Active subscriptions | Currently active, unexpired subscriptions |
| Revenue total / today | Sum of successful payments |
| Queue length | Jobs currently waiting in the Redis download queue |
| Downloads by status | Breakdown: queued / processing / completed / failed |

**Health badges** (data from `GET /api/admin/system/health`) show live status for **API**, **Database**, and **Redis**, plus the running **version** (from the root `VERSION` file). A red badge means that dependency is failing — check `zed-downloader logs api` first.

## Users page

- **Search** by Telegram ID, username, or name; results are paginated.
- Each row shows telegram_id, name/username, language, total downloads, blocked state, and join date.
- **Block / Unblock**: a blocked user gets `status:"denied", reason:"blocked"` on every download request; blocking never deletes data.
- Open a user to edit details (`PATCH /api/admin/users/{id}`).

## Role model

Admin accounts have one role; the owner is special:

| Role | Intended access |
|---|---|
| `owner` | Everything — **bypasses all role checks**. Exactly one, seeded by the installer. |
| `super_admin` | Full management: users, groups, plans, payments, platforms, providers, settings |
| `support` | User-facing operations: view/search users, block/unblock, view downloads |
| `finance` | Plans, payments, revenue reporting |
| `content_manager` | Platforms, providers, forced-join channels, ads, bot-texts, plans |

Role checks are enforced server-side by the API — hiding a page in the panel is cosmetic, the API is the authority.

## Panel pages

Beyond the Dashboard and Users pages above, the following management pages are **implemented** and backed by the API in [API.md](API.md):

| Page | What it manages | Backing API |
|---|---|---|
| Groups | Enable/disable groups, per-group daily limit | `GET /api/admin/groups`, `PATCH /api/admin/groups/{id}` |
| Downloads | Read-only download-request history (filter by status/user) | `GET /api/admin/downloads`, `GET .../downloads/{id}` |
| Plans | Subscription plans, including `scope` = `user` / `group` | `GET/POST /api/admin/plans`, `PATCH/DELETE /api/admin/plans/{id}` |
| Payments | Payment history + revenue | `GET /api/admin/payments` |
| Platforms | Supported platforms (name, URL regex, order) | `GET/POST /api/admin/platforms`, `PATCH/DELETE /api/admin/platforms/{id}` |
| Providers | Download providers, priority, test & balance | `GET/POST /api/admin/providers`, `PATCH/DELETE /api/admin/providers/{id}`, `POST .../test`, `GET .../balance` |
| Settings | Key/value operational settings | `GET /api/admin/settings`, `GET/PUT /api/admin/settings/{key}` |
| Ads | Weighted ads sent around downloads | `GET/POST /api/admin/ads`, `PATCH/DELETE /api/admin/ads/{id}` |
| Forced-join | Channels users must join first | `GET/POST /api/admin/forced-join`, `PATCH/DELETE /api/admin/forced-join/{id}` |
| Bot-texts | Runtime-editable bot messages (overlay the shipped i18n) | `GET/POST /api/admin/bot-texts`, `PATCH/DELETE /api/admin/bot-texts/{id}` |

Notes:

- **Provider API keys are write-only.** You can set a key when creating/editing a provider, but the panel never displays it back — the Providers list shows only a `has_api_key` flag. Sending an empty key clears the stored one. See [API.md](API.md#catalog-router-platforms--providers).
- **Ads**, **Forced-join**, and **Bot-texts** feed the bot/worker at runtime (see [OPERATIONS.md](OPERATIONS.md) for ads and editable-texts behavior).
- **Plans** with `scope=group` are purchased from inside a Telegram group; see [PAYMENTS.md — Group subscription purchase](PAYMENTS.md#group-subscription-purchase).

## Remaining stubs (v2)

These panel pages are still stubs; their features are planned for v2 (see the [README roadmap](../README.md#roadmap-v2)):

| Stub page | Planned function |
|---|---|
| Languages | Manage active bot languages (the 14 remaining i18n JSONs) |
| Broadcast | Send a message to all users from the panel |
| Admins | Create/manage admin accounts and roles |
| Backup | Trigger/download backups from the panel (CLI `zed-downloader backup` works today) |
| Update | In-panel update (CLI `zed-downloader update` works today) |
| Health | Advanced health monitoring & alerting (live badges already exist on the Dashboard) |

Also planned: advanced statistics + CSV export.

See also: [INSTALL.md](INSTALL.md) · [PROVIDERS.md](PROVIDERS.md) · [PAYMENTS.md](PAYMENTS.md) · [OPERATIONS.md](OPERATIONS.md)
