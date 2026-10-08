#!/bin/sh
# YTA stock-Hermes entrypoint (Render).
# Boot: register the scan job, PRIME the poller seen-set so historical messages
# are not re-surfaced on the first tick, then serve the gateway in the foreground.
set -eu

cd /opt/hermes

# Register the 1-minute scan job (idempotent); tee its output to stdout.
echo "=== registering cron job ==="
/opt/hermes/register_cron.sh 2>&1 | tee -a /opt/hermes/logs/cron-register.log

# Prime the seen-set: run the poller once, discard output. This marks every
# already-existing history entry as seen so only genuinely NEW messages fire the
# agent from now on (avoids flooding the first tick with all history).
echo "=== priming poller seen-set (dedupe history) ==="
python /opt/hermes/scripts/yta_poll.py >/dev/null 2>&1 || echo "[prime] poller warned; continuing"
echo "[prime] done"

# Run the gateway in the foreground: Telegram home + cron ticker + agent.
echo "=== launching gateway (foreground) ==="
exec hermes gateway run 2>&1 | tee -a /opt/hermes/logs/gateway.log