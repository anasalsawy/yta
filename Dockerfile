FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    HERMES_HOME=/opt/hermes \
    PIP_NO_CACHE_DIR=1

# System deps for git install + runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    git curl ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /opt/hermes

# Prompt + scan/send scripts are baked in (system_prompt.md under prompts/)
COPY prompts/system_prompt.md /opt/hermes/prompts/system_prompt.md
COPY scripts/yta_poll.py /opt/hermes/scripts/yta_poll.py
COPY scripts/yta_send.py /opt/hermes/scripts/yta_send.py
COPY config.yaml /opt/hermes/config.yaml

# Install stock Hermes (hermes-agent) from the upstream git repo (main branch)
RUN pip install --upgrade pip && \
    pip install "git+https://github.com/NousResearch/hermes-agent.git@main"

# Boot entrypoint: register the 1-min scan job, start the gateway (Telegram
# home) in the background, then run the cron scheduler loop in the foreground.
# Uses HERMES_HOME for config/env. Secrets come from Render env vars, not image.
COPY docker/start.sh /opt/hermes/start.sh
COPY docker/register_cron.sh /opt/hermes/register_cron.sh
RUN mkdir -p /opt/hermes/logs && \
    chmod +x /opt/hermes/start.sh /opt/hermes/register_cron.sh

CMD ["/opt/hermes/start.sh"]