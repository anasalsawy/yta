"""YTA check tool — Hermes runs this when woken to READ all conversations itself.

Prints the CURRENT full state of every customer conversation across Facebook
Messenger, Instagram DMs, and WhatsApp, with recent message history per thread.
This is the "go check and act" surface: Hermes reads this real context and then
decides (reply / follow up / stay silent / escalate) on its own judgment. It
SENDS NOTHING — this tool only reads and reports.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BRIDGE = os.environ.get("YTA_WA_BRIDGE", "http://127.0.0.1:3000")
GRAPH = "https://graph.facebook.com/" + os.environ.get("META_GRAPH_API_VERSION", "v21.0")


def _secret(key: str) -> str:
    v = os.environ.get(key) or ""
    if v:
        return v
    for line in (ROOT.parent / ".env").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, val = line.split("=", 1)
            if k.strip() == key:
                return val.strip().strip('"').strip("'")
    raise SystemExit(f"missing secret: {key}")


def _fetch(url: str, token: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _read_fb_ig(token: str) -> list[dict]:
    out: list[dict] = []
    page_id = _secret("FACEBOOK_PAGE_ID")
    url = (f"{GRAPH}/me/conversations?fields=messages.limit(12){{"
           f"message,from{{id,name}},is_instagram,created_time}},"
           f"participants{{id,name}},updated_time&limit=200")
    try:
        data = _fetch(url, token)
    except Exception as exc:
        print(f"[CHECK ERROR fb/ig: {type(exc).__name__}: {exc}]", file=sys.stderr)
        return out
    for conv in data.get("data", []):
        msgs = conv.get("messages", {}).get("data", [])
        for m in msgs:
            frm = m.get("from") or {}
            if not frm.get("id") or frm.get("id") == page_id:
                continue  # our own sends
            out.append({
                "channel": "Instagram DM" if m.get("is_instagram") else "Facebook Messenger",
                "conv": conv.get("id"),
                "from_id": frm.get("id"),
                "from_name": frm.get("name") or frm.get("id"),
                "message": m.get("message") or "" ,
                "created_time": m.get("created_time") or "",
            })
    return out


def _read_whatsapp() -> list[dict]:
    out: list[dict] = []
    try:
        req = urllib.request.Request(BRIDGE + "/messages")
        with urllib.request.urlopen(req, timeout=15) as r:
            evs = json.loads(r.read().decode())
    except Exception as exc:
        print(f"[CHECK ERROR whatsapp: {type(exc).__name__}: {exc}]", file=sys.stderr)
        return out
    for ev in evs or []:
        mid = ev.get("messageId") or ""
        body = str(ev.get("body") or "").strip()
        own = bool(ev.get("fromMe"))
        sender = str(ev.get("senderId") or "")
        chat = str(ev.get("chatId") or "")
        number = re.sub(r"[:@].*", "", sender) or ""
        if not mid or not chat or not body or own or number == re.sub(r"[:@].*", "", chat):
            continue
        out.append({
            "channel": "WhatsApp",
            "conv": chat,
            "from_id": sender,
            "from_name": f"WA {number}",
            "message": body,
            "created_time": ev.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    return out


def main() -> None:
    token = _secret("FACEBOOK_PAGE_ACCESS_TKN")
    msgs = _read_fb_ig(token) + _read_whatsapp()
    # Group by conversation, oldest first.
    groups: dict[str, list[dict]] = {}
    for m in msgs:
        groups.setdefault(f"{m['channel']}::{m['conv']}", []).append(m)
    print("=== YTA CONVERSATION DUMP (current state) ===", flush=True)
    if not groups:
        print("No customer conversations found right now.", flush=True)
        return
    for ck, ms in sorted(groups.items(), key=lambda kv: max((x.get("created_time") or "") for x in kv[1])):
        ms_sorted = sorted(ms, key=lambda x: x.get("created_time") or "")
        print("\n[CONVERSATION]", ck, flush=True)
        for m in ms_sorted[-12:]:
            who = m["from_name"] if m["from_id"] not in ("", None) else "customer"
            print(f"  {m.get('created_time') or '?'} | {who}: {m.get('message') or '(media/empty)'}", flush=True)


if __name__ == "__main__":
    main()