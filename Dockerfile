# syntax=docker/dockerfile:1
FROM python:3.15-slim-bookworm@sha256:498829c717b1e59fc42f0e7865eafe4e04ca0f70a3769d4ae70ba218df54507c AS dependencies
WORKDIR /build
COPY requirements.txt .
RUN python -m pip install --no-cache-dir --only-binary=:all: --target=/dependencies -r requirements.txt

FROM python:3.15-slim-bookworm@sha256:498829c717b1e59fc42f0e7865eafe4e04ca0f70a3769d4ae70ba218df54507c
# Refresh Debian security packages on each uncached scheduled build.
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*
# Dependencies are installed in the build stage; no installer is needed at runtime.
RUN python -m pip uninstall --yes pip \
    && python -c "import ensurepip, shutil; shutil.rmtree(ensurepip.__path__[0])"
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
