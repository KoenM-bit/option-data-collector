# syntax=docker/dockerfile:1
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Europe/Amsterdam

WORKDIR /app

# System deps (minimal, wheels cover the rest)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy source
COPY app ./app

# Expose API port
EXPOSE 8080

# Entrypoint supports single-process (api) and all-in-one modes
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

RUN rm -f /etc/resolv.conf || true

ENTRYPOINT ["/app/entrypoint.sh"]
# Default mode: api (single service)
CMD ["api"]

