"""Installer / packaging smoke checks (no app import, no DB)."""
import glob
import re
import subprocess
from pathlib import Path

# tests/ -> apps/api -> apps -> <repo root>
REPO_ROOT = Path(__file__).resolve().parents[3]

REQUIRED_ENV_KEYS = [
    "DATABASE_URL",
    "REDIS_URL",
    "JWT_SECRET",
    "ENCRYPTION_KEY",
    "TELEGRAM_WEBHOOK_SECRET",
    "BOT_TOKEN",
    "ZARINPAL_MERCHANT_ID",
    "CORS_ORIGINS",
    "RATE_LIMIT_MAX_REQUESTS",
]

REQUIREMENTS_FILES = [
    REPO_ROOT / "apps" / "api" / "requirements.txt",
    REPO_ROOT / "apps" / "bot" / "requirements.txt",
]


def test_every_shell_script_passes_bash_n():
    scripts = sorted(glob.glob(str(REPO_ROOT / "scripts" / "*.sh")))
    assert scripts, "no scripts/*.sh found"
    for script in scripts:
        result = subprocess.run(
            ["bash", "-n", script], capture_output=True, text=True
        )
        assert result.returncode == 0, f"{script} failed bash -n:\n{result.stderr}"


def test_env_example_has_required_keys():
    text = (REPO_ROOT / ".env.example").read_text()
    missing = [k for k in REQUIRED_ENV_KEYS if not re.search(rf"(?m)^{re.escape(k)}=", text)]
    assert not missing, f".env.example missing keys: {missing}"


def test_requirements_are_one_dependency_per_line():
    try:
        from packaging.requirements import Requirement

        def check(dep: str) -> None:
            Requirement(dep)  # raises on anything that is not a single, valid req
    except ImportError:  # pragma: no cover - packaging is a test dep
        def check(dep: str) -> None:
            assert re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]*(\[[^\]]+\])?", dep)
            # A stray space (outside markers) would mean two deps on one line.
            assert " " not in dep.split(";")[0].strip()

    for path in REQUIREMENTS_FILES:
        assert path.is_file(), f"missing {path}"
        deps = [
            line.strip()
            for line in path.read_text().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]
        assert deps, f"{path} has no dependencies"
        for dep in deps:
            check(dep)
