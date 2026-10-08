#!/bin/sh
# Register the YTA 1-minute scan cron job on first boot.
set -eu
cd /opt/hermes

hermes cron create \
  --name "yta-scan" \
  --schedule "every 1m" \
  --monitor-script /opt/hermes/scripts/yta_poll.py \
  --workdir /opt/hermes \
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