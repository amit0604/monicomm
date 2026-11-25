# Monicomm API. Dependencies are installed at build time only: the running container never needs internet.
FROM python:3.12.8-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY --from=ghcr.io/astral-sh/uv:0.5.14 /uv /usr/local/bin/uv
WORKDIR /srv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
# Catchup volume: a new named volume takes this directory's owner, so the app user can write to it.
RUN useradd --system --uid 10001 monicomm \
 && mkdir -p /data/pcap && chown monicomm /data/pcap
USER monicomm
ENV PATH="/srv/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
