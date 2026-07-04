"""Shared test configuration.

The application binds its async SQLAlchemy engine to DATABASE_URL and reads
its whole configuration at *import* time (app.database.engine, app.config
via lru_cache). So every environment variable the app needs MUST be set
before the first `import app.*` runs — i.e. right here, at the top of
conftest, which pytest imports before collecting any test module.
"""
import asyncio
import os
from pathlib import Path

# --- 1. Environment: set BEFORE importing anything under `app`. ------------
from cryptography.fernet import Fernet  # noqa: E402  (import order is intentional)

_TESTS_DIR = Path(__file__).resolve().parent
_TEST_DB = _TESTS_DIR / "_test.db"

# A single shared sqlite *file* (not :memory:) so the module-level engine —
# created once at import time — sees a consistent schema across sessions.
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_TEST_DB}"
os.environ["REDIS_URL"] = "redis://x"
os.environ["JWT_SECRET"] = "test-secret"
os.environ["ENCRYPTION_KEY"] = Fernet.generate_key().decode()
os.environ["TELEGRAM_WEBHOOK_SECRET"] = "int-secret"
os.environ["OWNER_ADMIN_EMAIL"] = "owner@test.local"
os.environ["OWNER_ADMIN_PASSWORD"] = "owner-pass"
# Keep config deterministic regardless of the host environment.
os.environ.pop("FREE_DOWNLOADS_PER_DAY", None)

# Drop any stale db from a previous aborted run before the engine opens it.
try:
    _TEST_DB.unlink()
except FileNotFoundError:
    pass

# --- 2. Install the fake Redis before any code can call get_redis(). -------
import fakeredis.aioredis  # noqa: E402
import app.workers.queue as _queue  # noqa: E402

_queue._client = fakeredis.aioredis.FakeRedis(decode_responses=True)

# --- 3. Now it is safe to import the app's models / engine. ----------------
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402

from app import models  # noqa: E402,F401  (registers every table on Base.metadata)
from app.database import Base, SessionLocal, engine  # noqa: E402


@pytest.fixture(scope="session")
def event_loop():
    """One event loop for the whole session.

    The module-level async engine pools connections; a per-test loop would
    hand a connection created in a closed loop to the next test. A single
    session-wide loop keeps every pooled aiosqlite connection valid.
    """
    loop = asyncio.new_event_loop()
    yield loop
    loop.run_until_complete(engine.dispose())
    loop.close()
    try:
        _TEST_DB.unlink()
    except FileNotFoundError:
        pass


@pytest_asyncio.fixture
async def session():
    """Fresh schema + one AsyncSession per test.

    Dropping and recreating every table gives each test a clean database,
    which matters because several flows under test (payment verification)
    commit real rows.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with SessionLocal() as s:
        yield s
