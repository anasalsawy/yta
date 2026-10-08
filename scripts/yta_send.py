"""YTA send helper - reply to a customer, or mark a message as needing no reply.

  python scripts/yta_send.py <channel> <customer_id> '<text>'
      channel: messenger | instagram_dm | whatsapp
  python scripts/yta_send.py --no-reply <last_message_id>
      the customer's last message needs no answer (e.g. "ok thanks"); stops re-waking on it

Prints SENT <id> on success, or the platform's real error text on failure.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import yta_inbox as inbox  # noqa: E402


def _post(url: str, payload: dict, headers: dict) -> dict:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json", **headers})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")[:500]
        hint = ""
        if "2018278" in body or "outside of allowed window" in body.lower():
            hint = " (Meta 24-hour window has closed for this customer - escalate to Anas instead)"
        raise SystemExit(f"send failed: HTTP {exc.code}: {body}{hint}")
    except Exception as exc:
        raise SystemExit(f"send failed: {type(exc).__name__}: {exc}")


def main(argv: list[str]) -> None:
    if argv[:1] == ["--no-reply"] and len(argv) == 2:
        inbox.mark_handled(argv[1])
        print("MARKED_NO_REPLY", argv[1])
        return
    if len(argv) < 3:
        raise SystemExit(__doc__)
    channel, recipient, text = argv[0], argv[1], " ".join(argv[2:]).strip()
    if not text:
        raise SystemExit("send failed: empty message")
    if channel == "whatsapp":
        bridge = inbox.secret("YTA_WA_BRIDGE", "http://127.0.0.1:3000")
        chat = recipient if "@" in recipient else f"{recipient}@s.whatsapp.net"
        res = _post(bridge + "/send", {"chatId": chat, "message": text}, {})
        if not res.get("success"):
            raise SystemExit(f"send failed: bridge said {res}")
        print("SENT", res.get("messageId"))
        return
    if channel not in ("messenger", "instagram_dm"):
        raise SystemExit(f"send failed: unknown channel {channel!r} (messenger | instagram_dm | whatsapp)")
    token = inbox.secret("FACEBOOK_PAGE_ACCESS_TKN")
    res = _post(f"{inbox.GRAPH}/me/messages",
                {"recipient": {"id": recipient}, "message": {"text": text}, "messaging_type": "RESPONSE"},
                {"Authorization": "Bearer " + token})
    print("SENT", res.get("message_id", "SENT_NO_ID"))


if __name__ == "__main__":
    main(sys.argv[1:])
