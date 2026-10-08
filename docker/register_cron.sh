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
  "A customer message may have just arrived. Go CHECK everything and act on
   your own judgment: run \`python scripts/yta_check.py\` to read the real
   current state of ALL customer conversations (Facebook Messenger, Instagram
   DMs, WhatsApp) with full thread history. Decide for each conversation
   whether to reply, follow up, stay silent, or escalate to the owner (me)
   on Telegram — base every decision on what you actually read, never invent
   facts. Send any reply/follow-up yourself with
   \`python scripts/yta_send.py <channel> <from_id> '<text>'\`. Escalate to me
   any request for a price/quote/booking or a decision you cannot make alone.
   Never quote or book yourself. Then send me a short Telegram notice of what
   you found and did." \
  2>&1 | tee -a /opt/hermes/logs/cron-create.log

echo "=== hermes cron list ==="
hermes cron list 2>&1 | tee -a /opt/hermes/logs/cron-list.log