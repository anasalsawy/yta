"""Offline tests for the inbox / poller / check logic (fake Graph API)."""
import io
import os
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
os.environ.setdefault("FACEBOOK_PAGE_ACCESS_TKN", "test-token")

import yta_inbox as inbox  # noqa: E402
import yta_poll  # noqa: E402

PAGE, IG = "1000", "1784"


def iso(minutes_ago: float) -> str:
    t = datetime.fromtimestamp(time.time() - minutes_ago * 60, timezone.utc)
    return t.strftime("%Y-%m-%dT%H:%M:%S+0000")


def msg(mid, frm_id, text, minutes_ago, name="Curtis Major", username=None):
    frm = {"id": frm_id}
    if username:
        frm["username"] = username
    else:
        frm["name"] = name
    return {"id": mid, "message": text, "from": frm, "created_time": iso(minutes_ago)}


class FakeGraph:
    def __init__(self, messenger, instagram, fail_ig=False):
        self.messenger, self.instagram, self.fail_ig = messenger, instagram, fail_ig
        self.urls = []

    def __call__(self, url, token=None, timeout=20):
        self.urls.append(url)
        if "/me?fields" in url:
            return {"id": PAGE, "name": "YTA", "instagram_business_account": {"id": IG, "username": "yta_travel"}}
        if "platform=instagram" in url:
            if self.fail_ig:
                raise RuntimeError("HTTP 400: (#3) Application does not have the capability")
            return {"data": self.instagram}
        return {"data": self.messenger}


class InboxTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        inbox.STATE_DIR = Path(self.tmp.name)
        inbox.HANDLED_FILE = inbox.STATE_DIR / "handled.json"
        inbox.IDENTITY_FILE = inbox.STATE_DIR / "identity.json"
        # newest first, like the Graph API
        self.messenger = [
            {"id": "t_curtis", "messages": {"data": [
                msg("m3", "555", "October 19-22, 2 people", 2),
                msg("m2", PAGE, "Sure! Which dates?", 3, name="YTA"),
                msg("m1", "555", "I need a flight TPA to SAT", 4)]}},
            {"id": "t_done", "messages": {"data": [
                msg("d2", PAGE, "You're welcome!", 30, name="YTA"),
                msg("d1", "777", "thanks", 31, name="Nellie")]}},
            {"id": "t_old", "messages": {"data": [
                msg("o1", "888", "hello?", 60 * 30, name="Old Lead")]}},  # outside 24h window
        ]
        self.instagram = [
            {"id": "t_shaik", "messages": {"data": [
                msg("i2", "9001", "how much to Houston?", 15, username="shaik_arshad"),
                msg("i1", "9001", "hi", 16, username="shaik_arshad")]}},
            {"id": "t_ig_done", "messages": {"data": [
                msg("j2", IG, "Passed to our senior desk!", 5, username="yta_travel"),
                msg("j1", "9002", "book it", 6, username="buyer")]}},
        ]

    def tearDown(self):
        self.tmp.cleanup()

    def test_unanswered_sees_both_sides_and_both_platforms(self):
        g = FakeGraph(self.messenger, self.instagram)
        threads = inbox.all_threads(g)
        waiting = inbox.unanswered(threads)
        names = [t["customer_name"] for t in waiting]
        self.assertEqual(names, ["shaik_arshad", "Curtis Major"])  # oldest wait first
        curtis = waiting[1]
        self.assertEqual([m["text"] for m in curtis["pending"]], ["October 19-22, 2 people"])
        self.assertEqual(curtis["channel"], "messenger")
        self.assertEqual(waiting[0]["channel"], "instagram_dm")
        self.assertEqual(waiting[0]["customer_id"], "9001")
        # our own messages are recognised as ours
        full = [t for t in threads if t["conv"] == "t_curtis"][0]
        self.assertEqual([m["role"] for m in full["messages"]], ["customer", "us", "customer"])

    def test_instagram_failure_does_not_block_messenger(self):
        g = FakeGraph(self.messenger, self.instagram, fail_ig=True)
        waiting = inbox.unanswered(inbox.all_threads(g))
        self.assertEqual([t["customer_name"] for t in waiting], ["Curtis Major"])

    def test_no_reply_marking_and_retry_buckets(self):
        g = FakeGraph(self.messenger, self.instagram)
        out1 = yta_poll.render(inbox.unanswered(inbox.all_threads(g)))
        self.assertIn("status=waiting-10m+", out1)   # shaik has waited 16 min
        self.assertIn("status=new", out1)            # curtis 2 min
        inbox.mark_handled("i2")
        out2 = yta_poll.render(inbox.unanswered(inbox.all_threads(g)))
        self.assertNotIn("shaik_arshad", out2)
        self.assertIn("Curtis Major", out2)

    def test_output_is_stable_between_ticks(self):
        g = FakeGraph(self.messenger, self.instagram)
        a = yta_poll.render(inbox.unanswered(inbox.all_threads(g)))
        b = yta_poll.render(inbox.unanswered(inbox.all_threads(g)))
        self.assertEqual(a, b)  # same state -> same bytes -> Hermes does not wake the agent

    def test_nothing_waiting(self):
        self.assertEqual(yta_poll.render([]), "NO_UNANSWERED")

    def test_crash_does_not_lose_message(self):
        # the old poller marked messages seen when printed; a crash lost them. Now state decides.
        g = FakeGraph(self.messenger, self.instagram)
        first = inbox.unanswered(inbox.all_threads(g))
        again = inbox.unanswered(inbox.all_threads(g))  # e.g. after an OOM restart
        self.assertEqual([t["conv"] for t in first], [t["conv"] for t in again])

    def test_check_tool_prints_us_lines(self):
        import yta_check
        g = FakeGraph(self.messenger, self.instagram)
        orig = inbox.all_threads
        inbox.all_threads = lambda fetcher=g: orig(g)
        try:
            buf = io.StringIO()
            with redirect_stdout(buf):
                yta_check.main(["messenger", "555"])
        finally:
            inbox.all_threads = orig
        out = buf.getvalue()
        self.assertIn("US: Sure! Which dates?", out)
        self.assertIn("waiting for our reply", out)

    def test_parse_time_formats(self):
        self.assertGreater(inbox.parse_time("2026-10-08T21:00:00+0000"), 1.7e9)
        self.assertGreater(inbox.parse_time(1791496741000), 1.7e9)
        self.assertEqual(inbox.parse_time(""), 0.0)


if __name__ == "__main__":
    unittest.main()
