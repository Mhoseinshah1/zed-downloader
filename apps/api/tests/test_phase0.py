"""Phase 0 tests: crash-proof get_version, DB-free /health, and /ready that
returns 503 when the database or Redis is down."""
import app.config as config
import app.main as main


def test_get_version_safe_on_shallow_container_path(monkeypatch):
    """In the image __file__ is /app/app/config.py (3 parents). The old code
    did parents[3] and raised IndexError at import. The new code iterates, so
    it must return a non-empty string and never raise on a shallow path."""
    monkeypatch.delenv("APP_VERSION", raising=False)
    monkeypatch.setattr(config, "__file__", "/app/app/config.py")
    config.get_version.cache_clear()
    try:
        version = config.get_version()
    finally:
        config.get_version.cache_clear()
    assert isinstance(version, str) and version


def test_get_version_env_override(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "9.9.9")
    config.get_version.cache_clear()
    try:
        assert config.get_version() == "9.9.9"
    finally:
        config.get_version.cache_clear()


async def test_health_is_db_independent():
    """/health must not touch the DB/Redis — calling it returns ok with a
    version and never awaits a connection."""
    body = await main.health()
    assert body["status"] == "ok"
    assert body["version"]


async def test_ready_ok_when_db_and_redis_up(session):
    resp = await main.ready()
    assert resp.status_code == 200
    import json

    payload = json.loads(bytes(resp.body))
    assert payload["database"] == "ok" and payload["redis"] == "ok"


async def test_ready_503_when_db_down(session, monkeypatch):
    class _BrokenEngine:
        def connect(self):
            raise RuntimeError("db down")

    monkeypatch.setattr(main, "engine", _BrokenEngine())
    resp = await main.ready()
    assert resp.status_code == 503


async def test_ready_503_when_redis_down(session, monkeypatch):
    import app.workers.queue as queue

    class _BrokenRedis:
        async def ping(self):
            raise RuntimeError("redis down")

    monkeypatch.setattr(queue, "_client", _BrokenRedis())
    resp = await main.ready()
    assert resp.status_code == 503
