# Admin Panel Guide

The admin panel is a React 18 + Vite app (`apps/admin`) served by nginx and exposed through Caddy at `https://DOMAIN`. It consumes the admin API documented in [API.md](API.md).

## Login

- Open `https://DOMAIN` and sign in with e-mail + password.
- The **owner admin** account is created automatically by the installer on first API start, from the `OWNER_ADMIN_EMAIL` / `OWNER_ADMIN_PASSWORD` values in `.env` (see [INSTALL.md](INSTALL.md)).
- Sessions use short-lived JWT access tokens (`JWT_ACCESS_TTL_MINUTES`, default 30) that the panel refreshes automatically with the refresh token (`JWT_REFRESH_TTL_DAYS`, default 7). Logout invalidates the session.
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
| `content_manager` | Platforms, providers, forced-join channels |

Role checks are enforced server-side by the API — hiding a page in the panel is cosmetic, the API is the authority.

## Pages shipping in v2 (stubs today)

The following pages are stubs in v1. **Their APIs already exist** (see [API.md](API.md)) — the panel screens are what's pending, so you can automate against the API today:

| Stub page | Backing API |
|---|---|
| Groups | `GET /api/admin/groups`, `PATCH /api/admin/groups/{id}` |
| Plans | `GET/POST /api/admin/plans`, `PATCH/DELETE /api/admin/plans/{id}` |
| Payments | `GET /api/admin/payments` |
| Platforms | `GET/POST /api/admin/platforms`, `PATCH/DELETE /api/admin/platforms/{id}` |
| Providers | `GET/POST /api/admin/providers`, `PATCH/DELETE /api/admin/providers/{id}`, `POST .../test`, `GET .../balance` |

Also planned for v2 (see the [README roadmap](../README.md#roadmap-v2)): advanced statistics + CSV export, broadcast messaging, in-panel backup/update, health monitoring & alerts — roughly 18 panel pages in total.

See also: [INSTALL.md](INSTALL.md) · [PROVIDERS.md](PROVIDERS.md) · [PAYMENTS.md](PAYMENTS.md)
