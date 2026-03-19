FROM alpine:latest
LABEL maintainer="weedo078"

# Define package name
ARG PACKAGE_NAME=kuasarr

# install system deps
RUN apk add --no-cache \
    python3 \
    py3-pip \
    python3-dev \
    build-base

# allow pip to manage the system installation (PEP 668)
RUN mkdir -p ~/.config/pip && echo -e "[global]\nbreak-system-packages = true" > ~/.config/pip/pip.conf \
    && pip3 install --upgrade pip \
    && pip3 install wheel

# install local package (assumes .whl is in dist/ folder during build)
COPY dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm /tmp/*.whl && \
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
