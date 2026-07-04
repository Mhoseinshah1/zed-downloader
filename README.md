<div dir="rtl">

# زد دانلودر (Zed Downloader)

**پلتفرم دانلود از شبکه‌های اجتماعی برای تلگرام** — یک مجموعهٔ کامل و آمادهٔ استقرار شامل ربات تلگرام، سرویس API، ورکر دانلود و پنل مدیریت وب؛ همراه با اشتراک، درگاه پرداخت زرین‌پال و نصب خودکار روی سرور شما.

کاربر لینک یک پست عمومی (اینستاگرام، یوتیوب و…) را برای ربات می‌فرستد؛ سیستم فایل را دانلود کرده و همان‌جا در چت تحویل می‌دهد. مدیریت کاربران، پلن‌ها، پرداخت‌ها و ارائه‌دهنده‌های دانلود همگی از پنل مدیریت انجام می‌شود.

## ⚠️ اطلاعیهٔ حقوقی

> **این نرم‌افزار فقط برای دانلود محتوای عمومی و مجاز طراحی شده است.**
> هیچ بخشی از این پروژه ورود به حساب کاربری، دور زدن محدودیت‌ها، استفاده از کوکی/سشن یا دسترسی به محتوای خصوصی را پشتیبانی نمی‌کند و نخواهد کرد. ارائه‌دهنده‌هایی که به محتوای خصوصی برخورد کنند، درخواست را با خطای `private_content` رد می‌کنند. مسئولیت رعایت قوانین محلی و شرایط استفادهٔ هر پلتفرم بر عهدهٔ بهره‌بردار است.

## امکانات

- ربات تلگرام (aiogram 3) با پیام‌های **فارسی و انگلیسی** (ساختار آمادهٔ افزودن ۱۴ زبان دیگر)
- **متن‌های ربات قابل ویرایش از پنل**: پیام‌ها از دیتابیس روی i18n پیش‌فرض overlay می‌شوند (بدون نیاز به استقرار مجدد)
- دانلود از پلتفرم‌های مختلف با معماری «ارائه‌دهنده» (Provider) و جایگزینی خودکار (fallback) بر اساس اولویت
- محدودیت دانلود روزانهٔ رایگان + پلن‌های اشتراک قابل تعریف از پنل
- **اشتراک گروهی**: پلن مخصوص گروه از داخل همان گروه خریداری می‌شود و سهمیه بین اعضا مشترک است
- **محدودیت نرخ** درخواست‌ها به‌ازای هر کاربر و هر گروه (fixed-window مبتنی بر Redis، با رفتار fail-open)
- پرداخت با **زرین‌پال** (حالت سندباکس برای تست) — معماری آماده برای درگاه‌های بیشتر
- **تبلیغات وزن‌دار**: نمایش تصادفیِ آگهی فعال، قبل/بعد از دانلود، قابل مدیریت از پنل
- عضویت اجباری در کانال‌ها (Forced Join) قابل تنظیم
- پشتیبانی از گروه‌ها (فعال/غیرفعال‌سازی هر گروه)
- پنل مدیریت React با داشبورد آمار، مدیریت کاربران، نقش‌های ادمین و نشانگر سلامت سرویس‌ها
- **صف دانلود مطمئن** مبتنی بر Redis Streams (consumer group، بازیابی کارهای ورکرِ کرش‌کرده و dead-letter)؛ ورکر جدا از ربات، فایل را مستقیم به چت تلگرام ارسال می‌کند
- **سخت‌سازی امنیتی**: CORS پیش‌فرض same-origin، رمز عبور برای Redis، و باطل‌سازی توکن ادمین هنگام خروج (access + refresh)
- **CI و انتشار خودکار**: تست‌ها روی هر push/PR، و ساخت GitHub Release با tag نسخه
- نصب تک‌فرمانی با Docker Compose + Caddy (گواهی HTTPS خودکار)
- ابزار خط فرمان `zed-downloader` برای وضعیت، بروزرسانی، پشتیبان‌گیری و بازگردانی

## نصب سریع

پیش‌نیازها: سرور اوبونتو ۲۲.۰۴ یا ۲۴.۰۴ (حداقل ۲ گیگابایت رم)، یک دامنه با رکورد A به سمت سرور، و توکن ربات از [@BotFather](https://t.me/BotFather).

<div dir="ltr">

```bash
git clone https://github.com/mhoseinshah1/zed-downloader.git /opt/zed-downloader
cd /opt/zed-downloader
sudo bash scripts/install.sh
```

</div>

نصاب به‌صورت تعاملی دامنه، ایمیل، توکن ربات و مشخصات ادمین اصلی را می‌پرسد، رمزها و کلیدهای امنیتی را خودش تولید می‌کند، فایل `.env` را می‌سازد و همهٔ سرویس‌ها را بالا می‌آورد. راهنمای کامل: [docs/INSTALL.md](docs/INSTALL.md)

## دستورهای خط فرمان

پس از نصب، ابزار `zed-downloader` در دسترس است:

| دستور | کار |
|---|---|
| `zed-downloader status` | وضعیت کانتینرها و سلامت سرویس‌ها |
| `zed-downloader logs [service]` | نمایش لاگ‌ها |
| `zed-downloader start` / `stop` / `restart` | مدیریت سرویس‌ها |
| `zed-downloader update` | بروزرسانی امن با پشتیبان‌گیری و بازگشت خودکار در صورت خطا |
| `zed-downloader backup` | پشتیبان‌گیری از دیتابیس و تنظیمات (نگهداری ۱۰ نسخهٔ آخر) |
| `zed-downloader restore FILE` | بازگردانی از فایل پشتیبان |
| `zed-downloader set-webhook` | ثبت وبهوک تلگرام (در حالت webhook) |

## نقشهٔ راه (نسخهٔ ۲)

- درگاه‌های پرداخت زیبال، Telegram Stars، TON و TRON (USDT)
- ۱۴ فایل زبان باقی‌مانده (ساختار i18n از الان آماده است)
- صفحه‌های باقی‌ماندهٔ پنل (زبان‌ها، پیام همگانی، ادمین‌ها، پشتیبان‌گیری، بروزرسانی، پایش سلامت)
- آمار پیشرفته و خروجی CSV
- سرور خودمیزبان `telegram-bot-api` برای آپلود فایل‌های بزرگ‌تر از ۵۰ مگابایت

مستندات کامل (انگلیسی): [نصب](docs/INSTALL.md) · [بروزرسانی](docs/UPDATE.md) · [ارائه‌دهنده‌ها](docs/PROVIDERS.md) · [پرداخت‌ها](docs/PAYMENTS.md) · [مرجع API](docs/API.md) · [پنل مدیریت](docs/ADMIN.md) · [عملیات](docs/OPERATIONS.md) · [انتشار](docs/RELEASING.md)

</div>

---

# Zed Downloader

**A production Telegram social-media downloader platform** — a Telegram bot, a FastAPI backend, a download worker, and a React admin panel, shipped together with subscriptions, Zarinpal payments, and a one-command installer for your own server.

A user sends the link of a **public** post (Instagram, YouTube, ...) to the bot; the platform downloads the media and delivers the file right back into the chat. Users, plans, payments, platforms, and download providers are all managed from the web admin panel.

## ⚠️ Legal notice

> **This software downloads public, permitted content only.**
> No part of this project supports — or will ever support — login bypass, cookies, session/credential handling, or access to private content. Providers must reject anything that would require authentication with a `private_content` error. Operators are responsible for complying with local law and each platform's terms of service.

## Features

- Telegram bot (aiogram 3) with **Persian + English** messages, structured so 14 more languages can be dropped in as JSON files
- **Panel-editable bot texts**: messages are overlaid from the database onto the shipped i18n — no redeploy to reword the bot
- Multi-platform downloads through a pluggable **provider architecture** with priority-based automatic fallback
- Free daily download quota + subscription plans configurable from the panel
- **Group subscriptions**: a group-scope plan is bought from inside the group and its quota is shared by all members
- **Rate limiting**: per-user and per-group-chat fixed-window throttle on download requests (Redis-backed, fails open)
- **Zarinpal** payment gateway (sandbox toggle for testing); gateway registry ready for more
- **Weighted ads**: a random active ad sent before/after downloads, managed from the panel
- Forced channel join, group enable/disable, user blocking, maintenance mode
- React 18 admin panel: dashboard stats, user management, role-based admins, service health badges
- **Reliable download queue** on Redis Streams — consumer group, reclaim of jobs orphaned by a crashed worker, and a dead-letter stream; a dedicated worker (not the bot) uploads the file straight to the Telegram chat
- **Hardened by default**: same-origin CORS, a password-protected Redis, and admin logout that revokes both the access and refresh tokens
- **CI + automated releases**: per-component checks on every push/PR, and a tagged GitHub Release gated on the `VERSION` file
- One-command install with Docker Compose + Caddy (automatic HTTPS via Let's Encrypt)
- `zed-downloader` CLI for status, logs, update (with auto-rollback), backup, and restore

## Architecture

```
                          ┌──────────────────────────────────────────┐
        HTTPS (80/443)    │                Docker host               │
  Internet ──────────────▶│  ┌───────┐                               │
                          │  │ Caddy │── /api, /health ──▶ ┌───────┐ │
                          │  │ (TLS) │── /  (panel) ─────▶ │ admin │ │
                          │  └───┬───┘                     │ nginx │ │
                          │      │ webhook (:8080)         └───────┘ │
                          │      ▼                                   │
                          │  ┌───────┐   internal HTTP   ┌───────┐   │
   Telegram  ◀───────────▶│  │  bot  │ ────────────────▶ │  api  │   │
   (users)                │  └───────┘  X-Internal-Secret│ :8000 │   │
                          │                              └───┬───┘   │
                          │                    enqueue jobs  │       │
                          │  ┌────────┐      ┌───────┐       │       │
   Telegram  ◀────────────│  │ worker │ ◀────│ redis │ ◀─────┤       │
   (file upload)          │  └───┬────┘      └───────┘       │       │
                          │      │        ┌──────────┐       │       │
                          │      └───────▶│ postgres │◀──────┘       │
                          │               └──────────┘               │
                          └──────────────────────────────────────────┘
```

- **Caddy** terminates TLS and routes traffic to the API, the bot webhook, and the admin panel.
- **api** (FastAPI, port 8000) implements the admin API, the internal bot API, and payment callbacks; on start it runs migrations and seeds the owner admin.
- **bot** (aiogram 3) only *acknowledges* — queued / denied / buy prompts. It talks to the API over `/api/internal/*` with the `X-Internal-Secret` header.
- **worker** consumes the Redis queue, downloads via the provider chain, and delivers the file (and any per-error message) directly to the Telegram chat using the same `BOT_TOKEN`.
- **postgres** stores everything; **redis** is the queue.

## Quick install

Requirements: Ubuntu 22.04/24.04, 2 GB+ RAM, a domain with an A record pointing at the server, and a bot token from [@BotFather](https://t.me/BotFather).

```bash
git clone https://github.com/mhoseinshah1/zed-downloader.git /opt/zed-downloader
cd /opt/zed-downloader
sudo bash scripts/install.sh
```

The installer asks for your domain, ACME e-mail, bot token/username, owner-admin credentials, and run mode (polling/webhook); it generates all secrets (`POSTGRES_PASSWORD`, `JWT_SECRET`, `ENCRYPTION_KEY`, `TELEGRAM_WEBHOOK_SECRET`) into a single root `.env`, installs Docker if missing, builds and starts the stack, and registers the `zed-downloader` CLI. Full walkthrough: [docs/INSTALL.md](docs/INSTALL.md).

## CLI

<!-- NOTE: canonical command list lives in scripts/manage.sh; run `zed-downloader` with no arguments for the authoritative list. -->

| Command | What it does |
|---|---|
| `zed-downloader status` | Container status + service health |
| `zed-downloader logs [service]` | Tail logs (all services or one of: api, worker, bot, admin, postgres, redis, caddy) |
| `zed-downloader start` / `stop` / `restart` | Start / stop / restart the stack |
| `zed-downloader update` | Safe update: backup → pull → rebuild → migrate → health check → auto-rollback on failure ([docs/UPDATE.md](docs/UPDATE.md)) |
| `zed-downloader backup` | Dump database + config into a timestamped archive (last 10 kept) |
| `zed-downloader restore FILE` | Restore from a backup archive |
| `zed-downloader set-webhook` | Register the Telegram webhook (webhook mode) |

## Tech stack

| Layer | Technology |
|---|---|
| Backend API + worker | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic |
| Telegram bot | aiogram 3 |
| Admin panel | React 18, Vite (served by nginx) |
| Database | PostgreSQL |
| Queue / cache | Redis |
| Reverse proxy / TLS | Caddy (automatic Let's Encrypt) |
| Payments | Zarinpal v4 REST (sandbox toggle) |
| Downloaders | yt-dlp provider, Apify Instagram provider (extensible registry) |
| Deployment | Docker Compose, single root `.env` |

## Project layout

```
zed-downloader/
├── VERSION
├── .env.example          # canonical env vars (copied to .env by the installer)
├── apps/
│   ├── api/              # FastAPI backend + download worker
│   │   └── app/
│   │       ├── models/       # SQLAlchemy models (accounts, billing, catalog, content)
│   │       ├── providers/    # BaseProvider ABC + registry + ytdlp/apify providers
│   │       ├── payments/     # BasePaymentProvider ABC + Zarinpal gateway
│   │       ├── services/     # payment_service (money core), subscription_service
│   │       └── workers/      # Redis queue consumer / file delivery
│   ├── bot/              # aiogram 3 bot (handlers, keyboards, i18n fa/en)
│   └── admin/            # React 18 + Vite admin panel
├── deploy/               # docker-compose.yml, caddy/Caddyfile
├── scripts/              # install.sh, manage.sh, update.sh, backup.sh, restore.sh
└── docs/                 # INSTALL, UPDATE, PROVIDERS, PAYMENTS, API, ADMIN, OPERATIONS, RELEASING
```

## Documentation

| Doc | Contents |
|---|---|
| [docs/INSTALL.md](docs/INSTALL.md) | Requirements, installer walkthrough, verification, webhook vs polling, troubleshooting |
| [docs/UPDATE.md](docs/UPDATE.md) | Update flow, auto-rollback, backup/restore |
| [docs/PROVIDERS.md](docs/PROVIDERS.md) | Provider architecture, error codes, fallback policy, how to add a provider |
| [docs/PAYMENTS.md](docs/PAYMENTS.md) | Payment architecture, money-safety invariants, Zarinpal flow, adding a gateway |
| [docs/API.md](docs/API.md) | Full HTTP route reference (admin, internal, public) |
| [docs/ADMIN.md](docs/ADMIN.md) | Admin panel guide + role model |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Rate limiting, reliable queue, ads, editable texts, CORS/Redis/auth hardening |
| [docs/RELEASING.md](docs/RELEASING.md) | Versioning, tags, CI, and the release workflow |

## Roadmap (v2)

- Payment gateways: **Zibal**, **Telegram Stars**, **TON**, **TRON (USDT)**
- The remaining **14 language JSONs** (i18n structure already in place)
- The remaining **stub panel pages**: languages, broadcast, admins, backup, update, health monitoring (see [docs/ADMIN.md](docs/ADMIN.md#remaining-stubs-v2))
- Advanced statistics + CSV export
- Broadcast messages to users from the panel
- In-panel backup & update
- A self-hosted `telegram-bot-api` server to lift the ~50 MB bot-upload cap (for files up to `MAX_FILE_SIZE_MB`)

## License

<!-- NOTE: no LICENSE file is shipped at the repo root yet; until one is added, all rights are reserved by the project owner. -->
Proprietary — all rights reserved unless a `LICENSE` file in this repository states otherwise. The legal notice above applies to every deployment: public, permitted content only.
