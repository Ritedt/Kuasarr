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
    linux-headers \
    tzdata \
    py3-numpy \
    py3-opencv

# Create venv with system packages (for py3-opencv) and install local package
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN python3 -m venv $VIRTUAL_ENV --system-site-packages
COPY dist/*.whl /tmp/
# Install the wheel without deps, then install deps except opencv-python (using system py3-opencv)
RUN uv pip install /tmp/*.whl --no-deps && rm /tmp/*.whl && \
    uv pip install beautifulsoup4 bottle deathbycaptcha-official dukpy numpy pillow pycryptodomex requests urllib3 && \
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
