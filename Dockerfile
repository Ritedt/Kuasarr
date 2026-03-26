FROM alpine:latest
LABEL maintainer="Ritedt" \
      org.opencontainers.image.title="Kuasarr" \
      org.opencontainers.image.description="Bridges JDownloader 2 with Radarr, Sonarr and LazyLibrarian by emulating a Newznab indexer and SABnzbd client. Scrapes DDL sites, decrypts CAPTCHA-protected links, and dispatches downloads to JDownloader via My-JDownloader API." \
      org.opencontainers.image.url="https://github.com/Ritedt/Kuasarr" \
      org.opencontainers.image.source="https://github.com/Ritedt/Kuasarr" \
      org.opencontainers.image.licenses="MIT"

# Define package name
ARG PACKAGE_NAME=kuasarr

# Install uv (pinned version for reproducible builds)
COPY --from=ghcr.io/astral-sh/uv:0.11.0 /uv /usr/local/bin/uv

RUN apk add --no-cache \
    python3 \
    python3-dev \
    build-base \
    tzdata

# Create venv and install local package (assumes .whl is in dist/ folder during build)
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN python3 -m venv $VIRTUAL_ENV
COPY dist/*.whl /tmp/
RUN uv pip install /tmp/*.whl && rm /tmp/*.whl && \
    apk del build-base python3-dev

# runtime defaults
VOLUME /config
EXPOSE 9999
ENV PYTHONUNBUFFERED=1 \
    DOCKER="true" \
    INTERNAL_ADDRESS="" \
    EXTERNAL_ADDRESS="" \
    DISCORD="" \
    HOSTNAMES=""

# Restart loop: exit 0 = restart, exit non-zero = stop container
ENTRYPOINT ["sh", "-c", "while true; do kuasarr --port=9999 --internal_address=$INTERNAL_ADDRESS --external_address=$EXTERNAL_ADDRESS --discord=$DISCORD --hostnames=$HOSTNAMES; ret=$?; if [ $ret -ne 0 ]; then echo \"Kuasarr exited with error $ret, stopping...\"; exit $ret; fi; echo \"Kuasarr restarting... \"; sleep 2; done"]
