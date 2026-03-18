FROM python:3.12-slim AS base

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .

# Install dependencies only (not the project itself) so this layer is cached
RUN pip install --no-cache-dir $(python -c "\
import tomllib, pathlib; \
cfg = tomllib.loads(pathlib.Path('pyproject.toml').read_text()); \
print(' '.join(cfg['project']['dependencies']))")

COPY . .

ENV PORT=8000
EXPOSE ${PORT}

CMD sh -c "uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"
