#!/bin/sh
# YTA stock-Hermes entrypoint (Render).
# Boot: register the scan job, show what is waiting, then serve the gateway in the foreground.
set -eu

cd /opt/hermes

# The Telegram chat with Anas is the agent's home conversation: cron reports land there and are
# written into that chat's history (cron.mirror_delivery), so both sides are one agent.
export TELEGRAM_HOME_CHANNEL="${TELEGRAM_HOME_CHANNEL:-${RESERVATIONS_TELEGRAM_CHAT_ID:-}}"

# Register the 1-minute scan job (idempotent); tee its output to stdout.
echo "=== registering cron job ==="
/opt/hermes/register_cron.sh 2>&1 | tee -a /opt/hermes/logs/cron-register.log

# No priming step any more: the poller is state-based (a thread is "waiting" while the
# customer spoke last), so a restart re-surfaces anything still unanswered instead of
# silently marking it seen. One quick read here just logs what is waiting at boot.
echo "=== waiting threads at boot ==="
python /opt/hermes/scripts/yta_poll.py 2>&1 | head -40 || echo "[boot] poller warned; continuing"

# Run the gateway in the foreground: Telegram home + cron ticker + agent.
# Inject the ClawLink API key (Render env secret) into the baked config before boot,
# so the clawlink MCP server uses the real key. Repo never holds the value.
if [ -n "${CLAWLINK_API_KEY:-}" ] && grep -q "__CLAWLINK_API_KEY__" /opt/hermes/config.yaml; then
  _esc=$(printf '%s' "$CLAWLINK_API_KEY" | sed 's/[&/\\]/\\&/g')
  sed -i "s/__CLAWLINK_API_KEY__/${_esc}/g" /opt/hermes/config.yaml
  echo "=== injected CLAWLINK_API_KEY into config ==="
fi
echo "=== launching gateway (foreground) ==="
exec hermes gateway run 2>&1 | tee -a /opt/hermes/logs/gateway.log