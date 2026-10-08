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
  "Customer threads that are WAITING for a reply are listed in the monitor
   output above (each line: channel, customer_id, name, status, last_message_id,
   and the customer's unanswered messages). SPEED MATTERS - a customer is
   waiting on the other end. For EACH waiting thread, in order:
   1) read just that thread: \`python scripts/yta_check.py <channel> <customer_id>\`
      (lines marked US are what we already said - never repeat or contradict them);
   2) reply on your own judgment with
      \`python scripts/yta_send.py <channel> <customer_id> '<text>'\`, or, if it
      needs a price/quote/booking or a decision you cannot make, tell the customer
      it is with our senior desk and escalate to me on Telegram; if the message
      genuinely needs no reply (e.g. 'ok thanks'), run
      \`python scripts/yta_send.py --no-reply <last_message_id>\`.
   Do customers first. Do not create skills, edit memory or do any other
   housekeeping during this job. If the monitor says NO_UNANSWERED, answer with
   exactly [SILENT]. Otherwise finish with a short Telegram notice to me of what
   each customer said and what you did." \
  2>&1 | tee -a /opt/hermes/logs/cron-create.log

echo "=== hermes cron list ==="
hermes cron list 2>&1 | tee -a /opt/hermes/logs/cron-list.log