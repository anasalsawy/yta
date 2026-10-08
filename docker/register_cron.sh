#!/bin/sh
# Register the YTA 1-minute scan cron job on first boot.
# Do NOT swallow errors — surface the real create output for verification.
set -u
cd /opt/hermes

echo "=== hermes cron create (yta-scan) ==="
hermes cron create \
  --name "yta-scan" \
  --monitor-script yta_poll.py \
  --workdir /opt/hermes \
  --deliver "telegram:${RESERVATIONS_TELEGRAM_CHAT_ID}" \
  "every 1m" \
  "Process any NEW_MESSAGES per my operating instructions. For each new
   customer message: read context, respond as the agency using
   scripts/yta_send.py <channel> <from_id> '<text>', and escalate to the owner
   (Telegram senior desk) any request for a price/quote/booking or a decision
   I cannot make alone. Never quote or book myself." \
  2>&1 | tee -a /opt/hermes/logs/cron-create.log

echo "=== hermes cron list ==="
hermes cron list 2>&1 | tee -a /opt/hermes/logs/cron-list.log