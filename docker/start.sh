#!/bin/sh
# YTA stock-Hermes entrypoint (Render).
# 1. Background: boot the Telegram gateway (agent's persistent home).
# 2. Foreground: run the cron scheduler loop, which fires the 1-min scan job.
set -eu

cd /opt/hermes

# Register the 1-minute scan job (idempotent) so first boot wires the poller.
/opt/hermes/register_cron.sh > /opt/hermes/logs/cron-register.log 2>&1 || true

# Boot the gateway so the agent is reachable on Telegram immediately.
hermes gateway run > /opt/hermes/logs/gateway.log 2>&1 &
GATEWAY_PID=$!
echo "[start] gateway launched pid=$GATEWAY_PID"

# Wait for the cron scheduler (ridealong on the gateway) to be ready.
sleep 5
hermes cron status > /opt/hermes/logs/cron-status.log 2>&1 || true

# Foreground scheduler loop: tick due jobs (the 1-min scan) once per iteration.
echo "[start] cron tick loop starting"
while true; do
  hermes cron tick >> /opt/hermes/logs/cron.log 2>&1 || echo "[cron] tick error: $?" >> /opt/hermes/logs/cron.log
  sleep 60
done