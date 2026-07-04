# Updating, Backup & Restore

## `zed-downloader update`

One command performs a safe, roll-back-able update, runnable **from any directory**:

```bash
zed-downloader update
```

Remote variant — works even on a box where you have not `cd`'d into the install
dir yet (clones to `/opt/zed-downloader` first if the checkout is missing):

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/Mhoseinshah1/zed-downloader/main/scripts/remote-update.sh)
```

### Prerequisites

- The app was installed by `scripts/install.sh`: a git checkout at
  `/opt/zed-downloader` (override with `$ZED_DIR`) containing a `.env`.
- Docker with the compose plugin on `PATH`.
- No prompts: the update path is fully non-interactive (safe for cron/CI).

### What happens, step by step

```
 0. self-copy        update.sh re-executes itself from a temp copy under /tmp,
                     so the `git reset` below can safely replace the on-disk
                     script mid-run (the copy deletes itself when done)
 1. backup           scripts/backup.sh — pg_dump + .env snapshot. The update
                     ABORTS if no archive is produced; this archive is what a
                     rollback restores
 2. pull             git fetch origin --prune --tags &&
                     git reset --hard origin/<current-branch>
 3. rebuild          docker compose ... up -d --build  (APP_VERSION in .env is
                     synced to the new VERSION file first)
 4. migrate          the api container's entrypoint runs Alembic migrations
                     (and idempotent seeding) automatically on start
 5. health gate      up to ~90s: GET /health inside zed_api must return 200,
                     AND GET /ready must return 200 (database + Redis reachable).
                     If /ready returns 404 (endpoint not present in that build),
                     the gate falls back to /health alone
 6a. success         a row is written to update_history (status = success) and
                     the last line printed is exactly:
                        UPDATE OK: v<previous> -> v<new>
 6b. failure         AUTO-ROLLBACK: git reset --hard to the previous commit,
                     then FORCE=1 scripts/restore.sh <step-1 archive> restores
                     the database so it matches the rolled-back code (a forward
                     migration is undone). update_history records rolled_back,
                     and the last line printed is exactly:
                        UPDATE FAILED — rolled back to v<previous>
```

Notes:

- **Backups live in `/opt/zed-downloader/backups/`** (timestamped `.tar.gz`; the
  last 10 are kept). The pre-update archive from step 1 is a normal backup — you
  can also restore it manually later.
- Migrations run **on API start**, not as a separate command — step 3 is what triggers step 4.
- The version shown by `/health` and the panel comes from the root [`VERSION`](../VERSION) file (exported as `APP_VERSION`).
- Success is only claimed after the health gate passes — a broken update can never end with "UPDATE OK".

### If it fails

The updater rolls back automatically. To see why the new version failed:

```bash
zed-downloader logs api        # last 200 api log lines (add --follow to stream)
zed-downloader status          # container states + health
```

The api log usually contains the exact error (import crash, failed migration,
database auth). Fix the cause, push, and run `zed-downloader update` again.

## Manual update (equivalent steps)

<!-- NOTE: the installer's default location is /opt/zed-downloader; adjust paths if you cloned elsewhere. -->

```bash
cd /opt/zed-downloader

# 1. backup first — never skip this
zed-downloader backup            # or: bash scripts/backup.sh

# 2. pull the new code
git pull

# 3. rebuild + restart (api entrypoint migrates + seeds on start)
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d

# 4. verify
curl -fsS "https://$(grep ^DOMAIN= .env | cut -d= -f2)/health"
zed-downloader status
```

## Rollback

Automatic rollback fires when the post-update health check fails. To roll back manually:

```bash
cd /opt/zed-downloader
git log --oneline -5                 # find the previous commit
git checkout <previous-commit>
docker compose -f deploy/docker-compose.yml build
docker compose -f deploy/docker-compose.yml up -d
zed-downloader restore /opt/zed-downloader/backups/<pre-update-backup-file>
```

Rolling back **code** without restoring the **database** is only safe when the update contained no migrations; when in doubt, restore the pre-update backup — that is exactly what auto-rollback does.

## Backup

```bash
zed-downloader backup
```

Creates a timestamped archive containing a full `pg_dump` of the database plus the root `.env` (which holds `ENCRYPTION_KEY` — without it, encrypted provider API keys are unrecoverable). **Retention: the last 10 backups are kept**; older ones are pruned automatically. Copy important backups off the server.

## Restore

```bash
zed-downloader restore /opt/zed-downloader/backups/<backup-file>
```

Stops the app services, restores the database dump from the archive, and starts the stack again. Restoring overwrites current data — take a fresh backup first if the current state might still matter.

See also: [INSTALL.md](INSTALL.md) · [API.md](API.md) · [ADMIN.md](ADMIN.md)
