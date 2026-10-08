"""YTA check tool - read conversations (both sides) before replying. Sends nothing.

  python scripts/yta_check.py                      threads waiting for a reply (default)
  python scripts/yta_check.py <channel> <customer_id>   one full thread
  python scripts/yta_check.py --all                every recent thread

Lines marked "US" are what the agency already said - never repeat or contradict them.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yta_inbox as inbox  # noqa: E402


def show(t: dict) -> None:
    print(f"\n[THREAD] channel={t['channel']} customer_id={t['customer_id']} name=\"{t['customer_name']}\"")
    for m in t["messages"]:
        who = "US" if m["role"] == "us" else t["customer_name"]
        print(f"  {inbox.fmt_ts(m['ts'])} | {who}: {m['text'] or '(empty)'}  [id={m['id']}]")
    pending = inbox.pending_customer_messages(t)
    if pending:
        print(f"  -> waiting for our reply (last_message_id={pending[-1]['id']})")


def main(argv: list[str]) -> None:
    threads = inbox.all_threads()
    if len(argv) >= 2 and not argv[0].startswith("--"):
        channel, cid = argv[0], argv[1]
        picked = [t for t in threads if t["channel"] == channel and t["customer_id"] == cid]
        if not picked:
            picked = [t for t in threads if t["customer_id"] == cid]
        if not picked:
            print(f"No thread found for {channel} {cid}.")
        for t in picked:
            show(t)
        return
    picked = threads if "--all" in argv else inbox.unanswered(threads)
    print(f"=== {'ALL RECENT' if '--all' in argv else 'WAITING FOR REPLY'}: {len(picked)} thread(s) ===")
    for t in picked:
        show(t)


if __name__ == "__main__":
    main(sys.argv[1:])
