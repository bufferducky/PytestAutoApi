FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src:/app/platform/backend/src \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pyta-browsers
WORKDIR /app
COPY pyproject.toml README.md ./
# 依赖与源码分层：修业务代码无需重新下载 Python 依赖或 Chromium。
RUN python -c "import subprocess,sys,tomllib; p=tomllib.load(open('pyproject.toml','rb')); subprocess.check_call([sys.executable,'-m','pip','install','--no-cache-dir',*p['project']['dependencies']])"
ARG INSTALL_WEB_RUNNER=0
RUN if [ "$INSTALL_WEB_RUNNER" = "1" ]; then \
      python -c "import subprocess,sys,tomllib; p=tomllib.load(open('pyproject.toml','rb')); subprocess.check_call([sys.executable,'-m','pip','install','--no-cache-dir','--timeout','120',*p['project']['optional-dependencies']['web']])" \
      && python -m playwright install --with-deps chromium \
      && chmod -R a+rX /opt/pyta-browsers; \
    fi
COPY src ./src
COPY platform/backend/src ./platform/backend/src
COPY platform/backend/alembic.ini ./platform/backend/alembic.ini
COPY platform/backend/alembic ./platform/backend/alembic
RUN pip install --no-cache-dir --no-deps . \
    && chmod -R a+rX /app/src /app/platform/backend \
    && useradd --uid 10001 --create-home app \
    && mkdir /state && chown app:app /state
USER app
EXPOSE 8000
# 当前 worker 与 API 在同一进程，保持单 worker，避免重复调度。
CMD ["sh", "-c", "python -m alembic -c platform/backend/alembic.ini upgrade head && exec python -m uvicorn pyta_platform_backend.main:app --host 0.0.0.0 --port 8000 --workers 1"]
