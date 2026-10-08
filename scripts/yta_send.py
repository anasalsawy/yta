"""YTA send helper — lets the stock Hermes agent reply to a customer.

Usage (from within the agent's terminal tool):
  python yta_send.py <channel> <recipient> <message_text>

  channel    : messenger | instagram_dm | whatsapp
  recipient  : for messenger/instagram_dm -> the customer PSID / IG user id
               for whatsapp              -> chat id like '19180000000@s.whatsapp.net'
Sends the message and prints the Meta/bridge message id on success.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _secret(key: str) -> str:
    v = __import__("os").environ.get(key) or ""
    if v:
        return v
    for line in (ROOT.parent / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, val = line.split("=", 1)
            if k.strip() == key:
                return val.strip().strip('"').strip("'")
    raise SystemExit(f"missing secret: {key}")


def _graph_post(url: str, payload: dict, token: str) -> str:
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return str(json.loads(r.read().decode()).get("message_id", "SENT_NO_ID"))


def main() -> None:
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    channel, recipient, text = sys.argv[1], sys.argv[2], " ".join(sys.argv[3:])
    if channel == "whatsapp":
        bridge = _secret("YTA_WA_BRIDGE") or "http://127.0.0.1:3000"
        chat = recipient if "@" in recipient else f"{recipient}@s.whatsapp.net"
        body = json.dumps({"chatId": chat, "message": text}).encode()
        req = urllib.request.Request(bridge + "/send", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            res = json.loads(r.read().decode())
        if not res.get("success"):
            raise SystemExit("bridge send failed: %s" % res)
        print("SENT", res.get("messageId"))
        return
    # Messenger / Instagram DM both go through the page /me/messages endpoint.
    token = _secret("FACEBOOK_PAGE_ACCESS_TKN")
    version = "v" + _secret("META_GRAPH_API_VERSION").lstrip("v")
    url = f"https://graph.facebook.com/{version}/me/messages"
    payload = {
        "recipient": {"id": recipient},
        "message": {"text": text},
        "messaging_type": "RESPONSE",
        "access_token": token,
    }
    try:
        print("SENT", _graph_post(url, payload, token))
    except Exception as exc:
        raise SystemExit(f"send failed: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    main()