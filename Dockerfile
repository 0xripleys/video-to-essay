FROM ghcr.io/astral-sh/uv:latest AS uv

FROM python:3.14.5-slim-bookworm

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

COPY --from=uv /uv /uvx /usr/local/bin/

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock .python-version ./
COPY src ./src

RUN uv sync --frozen --no-dev

CMD ["sh", "-c", "uv run video-to-essay worker ${WORKER_NAME:-process}"]
