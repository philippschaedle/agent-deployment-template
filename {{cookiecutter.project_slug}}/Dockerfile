# syntax=docker/dockerfile:1
FROM python:{{cookiecutter.python_version}}-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies first so this layer only rebuilds when they change.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev

FROM python:{{cookiecutter.python_version}}-slim AS runtime

RUN useradd --create-home --uid 1000 agent
WORKDIR /app
COPY --from=builder --chown=agent:agent /app /app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER agent
EXPOSE 8080

CMD ["python", "-m", "agent"]
