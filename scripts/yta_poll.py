"""YTA 1-minute poller for stock Hermes.

Reads NEW customer messages from Facebook Messenger, Instagram DMs (both via the
page inbox, which already includes IG when the IG business account is linked to
the page), and WhatsApp (Baileys bridge). Prints only the NEW messages as JSON
to stdout; the Hermes cron job injects this output into the agent's turn each
minute. Tracks a seen-set in a local state file so each message is surfaced once.
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
STATE_FILE = ROOT / "state" / "seen.json"
BRIDGE = os.environ.get("YTA_WA_BRIDGE", "http://127.0.0.1:3000")
GRAPH = "https://graph.facebook.com/" + os.environ.get("META_GRAPH_API_VERSION", "v21.0")

# Allow an explicit HOST token in the deployed env, else read local .env.
def _page_token() -> str:
    t = os.environ.get("FACEBOOK_PAGE_ACCESS_TKN") or ""
    if t:
        return t
    envfile = ROOT.parent / ".env"
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() == "FACEBOOK_PAGE_ACCESS_TKN":
                    return v.strip().strip('"').strip("'")
    raise SystemExit("FACEBOOK_PAGE_ACCESS_TKN not set")


def _load_state() -> list[str]:
    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_state(seen: list[str]) -> None:
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(seen[-5000:]), encoding="utf-8")


def _fetch(url: str, token: str, timeout: int = 30) -> dict:
    req = urllib.request.Request(
        url, headers={"Authorization": "Bearer " + token})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def poll_fb_ig(token: str) -> list[dict]:
    """Return new customer messages from the page inbox (FB + IG)."""
    out: list[dict] = []
    # Page conversations carry both Messenger and (linked) Instagram DMs.
    url = (f"{GRAPH}/me/conversations?fields=messages.limit(5){{"
           f"message,from{{id,name}},is_instagram,created_time}},"
           f"participants{{id,name}},updated_time&limit=200")
    try:
        data = _fetch(url, token)
    except Exception as exc:
        print(f"POLL ERROR fb_ig: {type(exc).__name__}: {exc}", file=sys.stderr)
        return out
    for conv in data.get("data", []):
        msgs = conv.get("messages", {}).get("data", [])
        for m in msgs:
            frm = (m.get("from") or {})
            page_id = os.environ.get("FACEBOOK_PAGE_ID") or ""
            if not frm.get("id") or frm.get("id") == page_id:
                continue  # our own sends
            channel = "instagram_dm" if m.get("is_instagram") else "messenger"
            out.append({
                "channel": channel,
                "conv": conv.get("id"),
                "from_id": frm.get("id"),
                "from_name": frm.get("name"),
                "message": m.get("message") or "",
                "created_time": m.get("created_time"),
            })
    return out


def poll_whatsapp() -> list[dict]:
    """Return new customer WhatsApp messages from the Baileys bridge."""
    out: list[dict] = []
    try:
        req = urllib.request.Request(BRIDGE + "/messages")
        with urllib.request.urlopen(req, timeout=15) as r:
            evs = json.loads(r.read().decode())
    except Exception as exc:
        print(f"POLL ERROR wa: {type(exc).__name__}: {exc}", file=sys.stderr)
        return out
    for ev in evs or []:
        mid = ev.get("messageId") or ""
        body = str(ev.get("body") or "").strip()
        own = bool(ev.get("fromMe"))
        sender = str(ev.get("senderId") or "")
        chat = str(ev.get("chatId") or "")
        number = re.sub(r"[:@].*", "", sender) or ""
        if not mid or not chat or not body or own or number == re.sub(r"[:@].*", "", chat):
            continue  # skip our sends and empty
        out.append({
            "channel": "whatsapp",
            "conv": chat,
            "from_id": sender,
            "from_name": f"WA {number}",
            "message": body,
            "created_time": ev.get("timestamp") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        })
    return out


def poll_ig(token: str, ig_account_id: str) -> list[dict]:
    """Return new customer Instagram DM messages. Can raise/no-op if the Meta
    app lacks the Instagram capability (code 3) — treat that as non-fatal so
    FB/WhatsApp continue; this line fires once the app capability is approved."""
    out: list[dict] = []
    url = (f"{GRAPH}/{ig_account_id}/conversations?platform=instagram"
           f"&fields=id,participants{{id,username}},updated_time,"
           f"messages.limit(5){{message,from{{id,username}},created_time}}"
           f"&limit=100")
    data = _fetch(url, token)
    for conv in data.get("data", []):
        for m in (conv.get("messages") or {}).get("data", []):
            frm = m.get("from") or {}
            if not frm.get("id") or str(frm.get("id")) in {token, ig_account_id}:
                continue  # our own sends
            out.append({
                "channel": "instagram_dm",
                "conv": conv.get("id"),
                "from_id": frm.get("id"),
                "from_name": frm.get("username") or frm.get("id"),
                "message": m.get("message") or "",
                "created_time": m.get("created_time"),
            })
    return out


def main() -> None:
    token = _page_token()
    ig_account_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID") or \
        os.environ.get("IG_ACCOUNT_ID") or "17841404406344891"
    seen = set(_load_state())
    new = []
    for m in poll_fb_ig(token):
        key = f"{m['channel']}|{m['conv']}|{m['from_id']}|{m.get('created_time')}|{m['message'][:40]}"
        if key not in seen:
            seen.add(key)
            new.append(m)
    try:
        for m in poll_ig(token, ig_account_id):
            key = f"{m['channel']}|{m['conv']}|{m['from_id']}|{m.get('created_time')}|{m['message'][:40]}"
            if key not in seen:
                seen.add(key)
                new.append(m)
    except Exception as exc:
        print(f"POLL NOTE ig (non-fatal): {type(exc).__name__}: {exc}", file=sys.stderr)
    for m in poll_whatsapp():
        key = f"{m['channel']}|{m['conv']}|{m['from_id']}|{m.get('created_time')}|{m['message'][:40]}"
        if key not in seen:
            seen.add(key)
            new.append(m)
    _save_state(list(seen))
    if new:
        print("NEW_MESSAGES " + json.dumps(new, ensure_ascii=False))


if __name__ == "__main__":
    main()