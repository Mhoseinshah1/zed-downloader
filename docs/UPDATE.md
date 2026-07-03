# Updating, Backup & Restore

## `zed-downloader update`

One command performs a safe, roll-back-able update:

```bash
zed-downloader update
```

Flow:

```
 1. backup            pg_dump + .env snapshot (same as `zed-downloader backup`)
 2. git pull          fetch the new code (current commit is remembered for rollback)
 3. rebuild           docker compose build for changed images
 4. restart           docker compose up -d
 5. migrate           the api container's entrypoint runs Alembic migrations
                      (and seeding) automatically on start — no manual step
 6. health check      wait for GET /health to return ok
 7a. success          a row is written to the `update_history` table
                      (previous version → new version, status = success)
 7b. failure          AUTO-ROLLBACK: git checkout of the previous commit,
                      rebuild, restart, restore the pre-update DB backup;
                      update_history records the failed attempt
```

Notes:

- Migrations run **on API start**, not as a separate command — step 4 is what triggers step 5.
- The version shown in the panel and in `GET /api/admin/system/health` comes from the root [`VERSION`](../VERSION) file.
- Because a backup is taken first, even a failed migration is recoverable: rollback restores the database dump taken in step 1.

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
