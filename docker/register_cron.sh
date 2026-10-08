#!/bin/sh
# Register the YTA 1-minute scan cron job on first boot.
set -eu
cd /opt/hermes

# The monitor script prints NEW_MESSAGES <json> only when new customer
# messages arrived; unchanged output (empty) suppresses the agent run, so the
# agent ONLY wakes up when there's something to handle. This is the stock
# Hermes monitor-script pattern — no inventing a scheduler.
hermes cron create \
  --name "yta-scan" \
  --schedule "every 1m" \
  --monitor-script yta_poll.py \
  --deliver "telegram:${RESERVATIONS_TELEGRAM_CHAT_ID}" \
  "Process any NEW_MESSAGES per my operating instructions. For each new
   customer message: read context, respond as the agency using
   scripts/yta_send.py <channel> <from_id> '<text>', and escalate to the owner
   (Telegram senior desk) any request for a price/quote/booking or a decision
   I cannot make alone. Never quote or book myself." \
  > /opt/hermes/logs/cron-create.log 2>&1 || true

echo "[cron] job registered (or already present)"
hermes cron list > /opt/hermes/logs/cron-list.log 2>&1 || true
cat /opt/hermes/logs/cron-list.log