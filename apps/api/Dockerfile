FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# ffmpeg: yt-dlp merges video+audio; curl: container healthcheck.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Build-time import gate: fail the BUILD (fast, obvious) if the app can't be
# imported — instead of shipping an image whose uvicorn crashes on startup and
# only surfaces as a 120s health-check timeout. Dummy env satisfies the
# required settings; engine creation is lazy so no real DB is touched. This is
# run from WORKDIR /app, so it exercises the real container __file__ paths.
RUN DATABASE_URL="sqlite+aiosqlite:///tmp/build_check.db" \
    REDIS_URL="redis://localhost:6379/0" \
    JWT_SECRET="build-check" \
    python -c "from app.main import app; print('[build] import OK:', app.title, app.version)"

EXPOSE 8000

ENTRYPOINT ["/entrypoint.sh"]
# Role argument: "api" (migrate + seed + uvicorn) or "worker" (queue runner).
CMD ["api"]
