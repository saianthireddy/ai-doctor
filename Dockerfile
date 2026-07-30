# Multi-stage: the wheel is built with build tooling that the runtime never needs.
FROM python:3.12-slim AS builder

WORKDIR /build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --upgrade pip build && python -m build --wheel


FROM python:3.12-slim AS runtime

# Non-root: the process only ever reads uploads and writes its own data dir.
RUN useradd --create-home --uid 10001 aidoctor
WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    DATABASE_URL=sqlite:////app/data/aidoctor.db \
    VECTOR_BACKEND=qdrant

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl && mkdir -p /app/data && chown -R aidoctor /app

USER aidoctor
EXPOSE 8000

# Uses the app's own health endpoint, so an unhealthy container is one that
# cannot actually answer, not merely one whose process is alive.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health').status==200 else 1)"

CMD ["uvicorn", "aidoctor.main:app", "--host", "0.0.0.0", "--port", "8000"]
