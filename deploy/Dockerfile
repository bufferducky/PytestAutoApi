FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app/platform/backend/src
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY platform/backend/src ./platform/backend/src
COPY platform/backend/alembic.ini ./platform/backend/alembic.ini
COPY platform/backend/alembic ./platform/backend/alembic
RUN pip install --no-cache-dir . \
    && useradd --uid 10001 --create-home app \
    && mkdir /state && chown app:app /state
USER app
EXPOSE 8000
# 当前 worker 与 API 在同一进程，保持单 worker，避免重复调度。
CMD ["sh", "-c", "python -m alembic -c platform/backend/alembic.ini upgrade head && exec python -m uvicorn pyta_platform_backend.main:app --host 0.0.0.0 --port 8000 --workers 1"]
