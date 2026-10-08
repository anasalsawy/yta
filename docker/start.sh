#!/bin/sh
# YTA stock-Hermes entrypoint (Render).
# Boot: register the scan job, show what is waiting, then serve the gateway in the foreground.
set -eu

cd /opt/hermes

# Register the 1-minute scan job (idempotent); tee its output to stdout.
echo "=== registering cron job ==="
/opt/hermes/register_cron.sh 2>&1 | tee -a /opt/hermes/logs/cron-register.log

# No priming step any more: the poller is state-based (a thread is "waiting" while the
# customer spoke last), so a restart re-surfaces anything still unanswered instead of
# silently marking it seen. One quick read here just logs what is waiting at boot.
echo "=== waiting threads at boot ==="
python /opt/hermes/scripts/yta_poll.py 2>&1 | head -40 || echo "[boot] poller warned; continuing"

# Run the gateway in the foreground: Telegram home + cron ticker + agent.
echo "=== launching gateway (foreground) ==="
exec hermes gateway run 2>&1 | tee -a /opt/hermes/logs/gateway.log