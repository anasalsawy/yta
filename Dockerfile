FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    HERMES_HOME=/opt/hermes \
    HERMES_INSTALL_DIR=/opt/hermes/hermes-agent \
    PATH="/opt/hermes/hermes-agent/.hermes/bin:$PATH" \
    PIP_NO_CACHE_DIR=1

# System deps: bash (installer needs it), git, curl, build toolchain for a few
# native deps in the venv, plus pkg-config/libssl which some wheels need.
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash git curl ca-certificates build-essential \
    pkg-config libssl-dev ffmpeg ripgrep && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /root

# Install the official stock Hermes (uv-managed source tree). The installer
# refuses to pip-build a wheel, so we use its own supported path.
RUN curl -fsSL https://hermes-agent.nousresearch.com/install.sh -o /tmp/install-hermes.sh && \
    bash /tmp/install-hermes.sh

# Bake the Telegram adapter's and web search's Python deps into the image. Without this,
# Hermes lazy-installs them on EVERY boot ("Installing Python dependencies…", ~60 s) and that
# install pushed the 512 MB instance over its memory limit -> OOM kill -> reboot -> install
# again: a crash loop that left customer messages waiting for many minutes.
RUN hermes pm install --extra telegram --extra exa

# Bake the YTA config, system prompt, and scan/send scripts into the Hermes home.
COPY config.yaml /opt/hermes/config.yaml
COPY prompts/system_prompt.md /opt/hermes/prompts/system_prompt.md
COPY scripts/yta_inbox.py /opt/hermes/scripts/yta_inbox.py
COPY scripts/yta_poll.py /opt/hermes/scripts/yta_poll.py
COPY scripts/yta_send.py /opt/hermes/scripts/yta_send.py
COPY scripts/yta_check.py /opt/hermes/scripts/yta_check.py
COPY docker/start.sh /opt/hermes/start.sh
COPY docker/register_cron.sh /opt/hermes/register_cron.sh
RUN mkdir -p /opt/hermes/logs /opt/hermes/state && \
    chmod +x /opt/hermes/start.sh /opt/hermes/register_cron.sh

CMD ["/opt/hermes/start.sh"]