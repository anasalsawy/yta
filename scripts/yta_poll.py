"""YTA monitor for the Hermes cron job (runs every minute, costs no LLM tokens).

Prints every conversation that is still waiting for us (the customer spoke last),
with the messages that need answering. Hermes wakes the agent only when this
output changes: a new customer message, a thread got answered, or a thread has
been waiting 10 / 30 / 90 minutes (automatic retry if a reply failed).

State-based on purpose: there is no consume-once "seen" list, so a crash, an
out-of-memory restart, or a skipped tick can never swallow a customer message.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yta_inbox as inbox  # noqa: E402


def render(waiting: list[dict]) -> str:
    if not waiting:
        return "NO_UNANSWERED"
    lines = [f"UNANSWERED_THREADS {len(waiting)}"]
    for t in waiting:
        last = t["pending"][-1]
        lines.append(f"- channel={t['channel']} customer_id={t['customer_id']} name=\"{t['customer_name']}\" "
                     f"status={inbox.bucket(t['waiting_s'])} last_message_id={last['id']}")
        for m in t["pending"][-5:]:
            text = (m["text"] or "(empty)").replace("\n", " ")[:400]
            lines.append(f"    customer @ {inbox.fmt_ts(m['ts'])}: {text}")
    return "\n".join(lines)


def main() -> None:
    print(render(inbox.unanswered(inbox.all_threads())))


if __name__ == "__main__":
    main()
