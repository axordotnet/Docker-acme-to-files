# syntax=docker/dockerfile:1
FROM python:3.15-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9 AS dependencies
WORKDIR /build
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --only-binary=:all: --target=/dependencies -r requirements.txt

FROM python:3.15-slim-bookworm@sha256:96599df822d0e1c6bb700014a05c7f3c8cabc6e0f7ff3c4f9f69cee033b4b5d9
# Refresh Debian security packages on each uncached scheduled build.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
LABEL org.opencontainers.image.title="Docker-acme-to-files" \
      org.opencontainers.image.description="Offline Traefik ACME certificate exporter" \
      org.opencontainers.image.source="https://github.com/axordotnet/Docker-acme-to-files" \
      org.opencontainers.image.licenses="MIT"
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app:/dependencies
COPY --from=dependencies /dependencies /dependencies
COPY src/ /app/
COPY LICENSE /licenses/Docker-acme-to-files-LICENSE
RUN mkdir /input /output && chown 10001:10001 /output
USER 10001:10001
WORKDIR /app
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD ["python", "-m", "acme_to_files", "--healthcheck"]
ENTRYPOINT ["python", "-m", "acme_to_files"]
