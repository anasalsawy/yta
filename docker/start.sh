#!/bin/sh
# YTA stock-Hermes entrypoint (Render).
# Stock pattern: the Hermes gateway process owns BOTH the Telegram home AND the
# cron scheduler, so we just run it in the foreground. One process, no double-fire.
set -eu

cd /opt/hermes

# Register the 1-minute scan job (idempotent); tee its output to stdout.
echo "=== registering cron job ==="
/opt/hermes/register_cron.sh 2>&1 | tee -a /opt/hermes/logs/cron-register.log

# Run the gateway in the foreground: Telegram home + cron ticker + agent.
echo "=== launching gateway (foreground) ==="
exec hermes gateway run 2>&1 | tee -a /opt/hermes/logs/gateway.log