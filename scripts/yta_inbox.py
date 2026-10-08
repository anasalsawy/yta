"""YTA inbox reader shared by the poller and the check tool.

Reads every customer thread on Facebook Messenger and Instagram (through the
page token) and WhatsApp (Baileys bridge, only when YTA_WA_BRIDGE is set) with
BOTH sides of the conversation, oldest first, so the agent always sees what it
already said.

"Unanswered" is computed from state, not from a consume-once seen list: a
thread is unanswered when its newest message is from the customer. Nothing is
ever lost to a crash or a restart - if the agent dies mid-reply, the thread is
still unanswered on the next tick.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "state"
HANDLED_FILE = STATE_DIR / "handled.json"
IDENTITY_FILE = STATE_DIR / "identity.json"
GRAPH = "https://graph.facebook.com/v" + os.environ.get("META_GRAPH_API_VERSION", "21.0").lstrip("v")
# Meta only allows a normal reply within 24h of the customer's last message.
REPLY_WINDOW_HOURS = float(os.environ.get("YTA_REPLY_WINDOW_HOURS", "23"))
THREADS_PER_PLATFORM = int(os.environ.get("YTA_THREADS_PER_PLATFORM", "40"))
MESSAGES_PER_THREAD = int(os.environ.get("YTA_MESSAGES_PER_THREAD", "25"))


def secret(key: str, default: str | None = None) -> str:
    v = os.environ.get(key) or ""
    if v:
        return v
    envfile = ROOT.parent / ".env"
    if envfile.exists():
        for line in envfile.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, val = line.split("=", 1)
                if k.strip() == key:
                    return val.strip().strip('"').strip("'")
    if default is not None:
        return default
    raise SystemExit(f"missing secret: {key}")


def fetch(url: str, token: str | None = None, timeout: int = 20) -> dict:
    headers = {"Authorization": "Bearer " + token} if token else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as exc:  # surface Meta's real error text
        body = exc.read().decode(errors="replace")[:400]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from None


def parse_time(value) -> float:
    if value is None or value == "":
        return 0.0
    if isinstance(value, (int, float)):
        v = float(value)
        return v / 1000 if v > 1e12 else v
    s = str(value).strip()
    if s.isdigit():
        return parse_time(int(s))
    s = s.replace("Z", "+00:00")
    if re.search(r"[+-]\d{4}$", s):  # Graph uses +0000
        s = s[:-2] + ":" + s[-2:]
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return 0.0
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _save_json(path: Path, value) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value), encoding="utf-8")
    tmp.replace(path)


def identity(token: str, fetcher=fetch) -> dict:
    """Our own ids (page + linked Instagram account), so our replies are recognised."""
    ident = _load_json(IDENTITY_FILE, {})
    if ident.get("page_id"):
        return ident
    ident = {"page_id": os.environ.get("FACEBOOK_PAGE_ID", ""),
             "ig_id": os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID") or os.environ.get("IG_ACCOUNT_ID", "")}
    try:
        me = fetcher(f"{GRAPH}/me?fields=id,name,instagram_business_account%7Bid,username%7D", token)
        ident["page_id"] = ident["page_id"] or str(me.get("id", ""))
        iba = me.get("instagram_business_account") or {}
        ident["ig_id"] = ident["ig_id"] or str(iba.get("id", ""))
        ident["ig_username"] = iba.get("username", "")
    except Exception as exc:
        print(f"[inbox] identity lookup failed: {exc}", file=sys.stderr)
    if ident.get("page_id"):
        _save_json(IDENTITY_FILE, ident)
    return ident


def _graph_threads(token: str, platform: str, ours: set[str], fetcher=fetch,
                   our_usernames: frozenset = frozenset()) -> list[dict]:
    fields = (f"id,updated_time,participants,messages.limit({MESSAGES_PER_THREAD})"
              "{id,message,from,created_time,attachments}")
    url = (f"{GRAPH}/me/conversations?platform={platform}&limit={THREADS_PER_PLATFORM}"
           f"&fields={urllib.parse.quote(fields, safe=',(){}._')}")
    data = fetcher(url, token)
    channel = "instagram_dm" if platform == "instagram" else "messenger"
    threads = []
    for conv in data.get("data", []):
        msgs = []
        customer_id, customer_name = "", ""
        for m in (conv.get("messages") or {}).get("data", []):
            frm = m.get("from") or {}
            fid = str(frm.get("id", ""))
            who_us = fid in ours or (frm.get("username") or "") in our_usernames
            text = (m.get("message") or "").strip()
            if not text and (m.get("attachments") or {}).get("data"):
                text = "(sent an attachment)"
            msgs.append({"id": m.get("id", ""), "ts": parse_time(m.get("created_time")),
                         "role": "us" if who_us else "customer", "text": text})
            if not who_us and fid and not customer_id:
                customer_id = fid
                customer_name = frm.get("name") or frm.get("username") or fid
        if not customer_id:  # thread where only we spoke: find the other participant
            for p in (conv.get("participants") or {}).get("data", []):
                pid = str(p.get("id", ""))
                if pid and pid not in ours:
                    customer_id, customer_name = pid, p.get("name") or p.get("username") or pid
                    break
        msgs.sort(key=lambda x: (x["ts"], x["id"]))
        if customer_id:
            threads.append({"channel": channel, "conv": conv.get("id", ""), "customer_id": customer_id,
                            "customer_name": customer_name, "messages": msgs})
    return threads


def _whatsapp_threads() -> list[dict]:
    bridge = os.environ.get("YTA_WA_BRIDGE", "")
    if not bridge:
        return []  # bridge not deployed: don't spam errors every minute
    try:
        with urllib.request.urlopen(urllib.request.Request(bridge + "/messages"), timeout=10) as r:
            evs = json.loads(r.read().decode())
    except Exception as exc:
        print(f"[inbox] whatsapp: {type(exc).__name__}: {exc}", file=sys.stderr)
        return []
    by_chat: dict[str, dict] = {}
    for ev in evs or []:
        chat = str(ev.get("chatId") or "")
        body = str(ev.get("body") or "").strip()
        if not chat or not body:
            continue
        t = by_chat.setdefault(chat, {"channel": "whatsapp", "conv": chat, "customer_id": chat,
                                      "customer_name": "WA " + re.sub(r"[:@].*", "", chat), "messages": []})
        t["messages"].append({"id": str(ev.get("messageId") or ""), "ts": parse_time(ev.get("timestamp")),
                              "role": "us" if ev.get("fromMe") else "customer", "text": body})
    for t in by_chat.values():
        t["messages"].sort(key=lambda x: (x["ts"], x["id"]))
    return list(by_chat.values())


FULL_HISTORY_CAP = int(os.environ.get("YTA_FULL_HISTORY_CAP", "10000"))  # safety stop only


def full_history(thread: dict, fetcher=fetch) -> dict:
    """The ENTIRE conversation, first message to last, by following Graph paging.
    WhatsApp threads come from the bridge and already hold everything it has."""
    if thread["channel"] not in ("messenger", "instagram_dm") or not thread.get("conv"):
        return thread
    token = secret("FACEBOOK_PAGE_ACCESS_TKN")
    ident = identity(token, fetcher)
    ours = {x for x in (ident.get("page_id"), ident.get("ig_id")) if x}
    usernames = {u for u in (ident.get("ig_username"),) if u}
    fields = urllib.parse.quote("id,message,from,created_time,attachments", safe=",")
    url = f"{GRAPH}/{thread['conv']}/messages?fields={fields}&limit=100"
    msgs, seen = [], set()
    while url and len(msgs) < FULL_HISTORY_CAP:
        try:
            page = fetcher(url, token)
        except Exception as exc:
            print(f"[inbox] full history for {thread['conv']}: {exc}", file=sys.stderr)
            break
        for m in page.get("data", []):
            if m.get("id") in seen:
                continue
            seen.add(m.get("id"))
            frm = m.get("from") or {}
            who_us = str(frm.get("id", "")) in ours or (frm.get("username") or "") in usernames
            text = (m.get("message") or "").strip()
            if not text and (m.get("attachments") or {}).get("data"):
                text = "(sent an attachment)"
            msgs.append({"id": m.get("id", ""), "ts": parse_time(m.get("created_time")),
                         "role": "us" if who_us else "customer", "text": text})
        url = (page.get("paging") or {}).get("next")
    if not msgs:
        return thread  # keep the recent window rather than show nothing
    msgs.sort(key=lambda x: (x["ts"], x["id"]))
    return {**thread, "messages": msgs, "complete": not url}


def all_threads(fetcher=fetch) -> list[dict]:
    token = secret("FACEBOOK_PAGE_ACCESS_TKN")
    ident = identity(token, fetcher)
    ours = {x for x in (ident.get("page_id"), ident.get("ig_id")) if x}
    usernames = frozenset(u for u in (ident.get("ig_username"),) if u)
    threads: list[dict] = []
    for platform in ("messenger", "instagram"):
        try:
            threads += _graph_threads(token, platform, ours, fetcher, usernames)
        except Exception as exc:
            print(f"[inbox] {platform}: {exc}", file=sys.stderr)
    threads += _whatsapp_threads()
    return threads


def handled_ids() -> set[str]:
    return set(_load_json(HANDLED_FILE, []))


def mark_handled(message_id: str) -> None:
    ids = _load_json(HANDLED_FILE, [])
    if message_id and message_id not in ids:
        ids.append(message_id)
        _save_json(HANDLED_FILE, ids[-2000:])


def pending_customer_messages(thread: dict) -> list[dict]:
    """Customer messages after our last reply (what still needs an answer)."""
    out = []
    for m in reversed(thread["messages"]):
        if m["role"] == "us":
            break
        out.append(m)
    return list(reversed(out))


def unanswered(threads: list[dict], now: float | None = None) -> list[dict]:
    now = now or time.time()
    handled = handled_ids()
    out = []
    for t in threads:
        pending = pending_customer_messages(t)
        if not pending:
            continue
        last = pending[-1]
        if last["id"] in handled:
            continue  # agent decided this needs no reply
        if last["ts"] and now - last["ts"] > REPLY_WINDOW_HOURS * 3600:
            continue  # outside Meta's reply window
        out.append({**t, "pending": pending, "waiting_s": max(0.0, now - pending[0]["ts"]) if pending[0]["ts"] else 0})
    out.sort(key=lambda t: t["pending"][0]["ts"])
    return out


def bucket(waiting_s: float) -> str:
    """Coarse wait bucket: the poller output changes when a thread has waited 10/30/90 min,
    so a reply that failed (crash, error) is retried without waiting for a new message."""
    m = waiting_s / 60
    if m < 10:
        return "new"
    if m < 30:
        return "waiting-10m+"
    if m < 90:
        return "waiting-30m+"
    return "waiting-90m+"


def fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M UTC") if ts else "?"
