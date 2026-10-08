"""YTA escalation ledger - the shared notebook between the 1-minute customer job and the
Telegram chat with Anas. Both are the same agent; this file is how a quote Anas sends on
Telegram finds the customer who is waiting for it, even across restarts and sessions.

  python scripts/yta_escalations.py add <channel> <customer_id> "<name>" "<what we need from Anas>"
  python scripts/yta_escalations.py list            open escalations (oldest first)
  python scripts/yta_escalations.py done <id> "<what was sent to the customer>"
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yta_inbox as inbox  # noqa: E402

LEDGER = inbox.STATE_DIR / "escalations.json"


def _load() -> list[dict]:
    return inbox._load_json(LEDGER, [])


def _save(rows: list[dict]) -> None:
    inbox._save_json(LEDGER, rows[-500:])


def add(channel: str, customer_id: str, name: str, need: str) -> dict:
    rows = _load()
    for r in rows:  # one open escalation per customer: update it
        if r["status"] == "open" and r["channel"] == channel and r["customer_id"] == customer_id:
            r["need"], r["updated_at"] = need, time.time()
            _save(rows)
            return r
    row = {"id": max([r["id"] for r in rows] or [0]) + 1, "channel": channel, "customer_id": customer_id,
           "name": name, "need": need, "status": "open", "created_at": time.time(), "updated_at": time.time(),
           "resolution": ""}
    rows.append(row)
    _save(rows)
    return row


def open_rows() -> list[dict]:
    return sorted([r for r in _load() if r["status"] == "open"], key=lambda r: r["created_at"])


def done(esc_id: int, resolution: str) -> dict | None:
    rows = _load()
    for r in rows:
        if r["id"] == esc_id:
            r["status"], r["resolution"], r["updated_at"] = "done", resolution, time.time()
            _save(rows)
            return r
    return None


def render(rows: list[dict]) -> str:
    if not rows:
        return "NO_OPEN_ESCALATIONS"
    lines = [f"OPEN_ESCALATIONS {len(rows)}"]
    for r in rows:
        lines.append(f"#{r['id']} channel={r['channel']} customer_id={r['customer_id']} name=\"{r['name']}\" "
                     f"since={inbox.fmt_ts(r['created_at'])}\n    needs: {r['need']}")
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    if not argv or argv[0] == "list":
        print(render(open_rows()))
    elif argv[0] == "add" and len(argv) >= 5:
        r = add(argv[1], argv[2], argv[3], " ".join(argv[4:]))
        print(f"ESCALATION #{r['id']} recorded for {r['name']} ({r['channel']} {r['customer_id']})")
    elif argv[0] == "done" and len(argv) >= 2:
        r = done(int(argv[1].lstrip("#")), " ".join(argv[2:]))
        print(f"ESCALATION #{argv[1]} closed" if r else f"no escalation #{argv[1]}")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
