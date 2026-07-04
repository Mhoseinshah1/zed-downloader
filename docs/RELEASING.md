# Releasing

zed-downloader ships as a Docker Compose app with a single source of version truth: the root [`VERSION`](../VERSION) file (e.g. `1.0.0`). A release is a **version marker** — there are no build artifacts to upload; deployments update by pulling code (see [UPDATE.md](UPDATE.md)). CI enforces that a git tag always matches `VERSION`.

## Versioning

- `VERSION` holds a plain semver string `X.Y.Z`.
- It is the single source of truth: `GET /api/admin/system/health` and the panel's version badge read it (see [ADMIN.md](ADMIN.md)), and the updater/rollback flow tracks it (see [UPDATE.md](UPDATE.md)).
- Release tags are `vX.Y.Z` — the same numbers with a leading `v`.

## Cutting a release

```bash
# 1. bump the version (edit the file so it reads e.g. 1.1.0)
echo "1.1.0" > VERSION

# 2. commit the bump
git add VERSION
git commit -m "Release v1.1.0"

# 3. tag it — the tag MUST equal the VERSION (CI enforces this)
git tag v1.1.0

# 4. push the commit and the tag
git push origin HEAD
git push origin v1.1.0
```

Pushing a `v*.*.*` tag triggers the **Release** workflow ([`.github/workflows/release.yml`](../.github/workflows/release.yml)):

1. It reads `VERSION` and strips the leading `v` from the tag.
2. If `tag != VERSION` it **fails the job** with an error (`Tag '…' does not match VERSION file '…'`). This is the discipline gate — always bump `VERSION` before tagging.
3. On match it publishes a **GitHub Release** for the tag with auto-generated notes (via `softprops/action-gh-release`).

> The tag must point at a commit whose `VERSION` file already contains the matching number — bump-and-commit **before** you tag.

## CI workflow

Every push and pull request to `main`, `master`, and `claude/**` runs **CI** ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) — five independent per-component jobs. No external Postgres/Redis is needed; the API tests use SQLite + `fakeredis`.

| Job | Runner | What it does |
|---|---|---|
| **api** | Python 3.12 | Installs `apps/api` deps, `py_compile`s the app, runs `pytest` (SQLite + fakeredis) |
| **bot** | Python 3.12 | `py_compile`s the aiogram bot |
| **admin** | Node 20 | `npm ci` (or `npm install`) then `npm run build` of the React panel |
| **scripts** | ubuntu | `bash -n scripts/*.sh` — shell syntax check of the install/manage/update/backup/restore scripts |
| **compose** | ubuntu | `docker compose -f deploy/docker-compose.yml --env-file .env.example config` — validates the compose file |

The Release workflow does not re-run these checks — merge to the default branch (which runs CI green) before tagging.

## How a release reaches a server

Releases are informational; a running deployment upgrades with the CLI:

```bash
zed-downloader update      # backup → git pull → rebuild → restart → migrate → health check
```

`git pull` brings the new commit **including its bumped `VERSION`**, which is what the panel/health then reports. If the post-update health check fails, `update` **auto-rolls-back** to the previous commit (and its previous `VERSION`) and restores the pre-update database backup. Full flow, manual steps, and rollback: [UPDATE.md](UPDATE.md).

## Release checklist

- [ ] Changes merged to the default branch with CI green.
- [ ] `VERSION` bumped and committed.
- [ ] `git tag vX.Y.Z` matches `VERSION` exactly.
- [ ] Tag pushed; the Release workflow went green and the GitHub Release exists.
- [ ] Deployments run `zed-downloader update` to pick it up.

See also: [UPDATE.md](UPDATE.md) · [OPERATIONS.md](OPERATIONS.md) · [INSTALL.md](INSTALL.md)
