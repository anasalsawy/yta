"""Boot scripts must hand Hermes exactly the arguments we mean (a stray quote once dropped the job)."""
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RegisterCronTests(unittest.TestCase):
    def test_cron_create_gets_one_prompt_argument(self):
        with tempfile.TemporaryDirectory() as d:
            fake = Path(d) / "hermes"
            fake.write_text('#!/bin/sh\nfor a in "$@"; do printf "ARG<%s>\\n" "$a"; done\n')
            fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
            home = Path(d) / "home"
            (home / "logs").mkdir(parents=True)
            script = (ROOT / "docker/register_cron.sh").read_text().replace("/opt/hermes", str(home))
            env = {**os.environ, "PATH": f"{d}:{os.environ['PATH']}", "RESERVATIONS_TELEGRAM_CHAT_ID": "1"}
            out = subprocess.run(["sh", "-c", script], capture_output=True, text=True, env=env).stdout
        create = out.split("=== hermes cron list ===")[0]
        args = [a.split(">")[0] for a in create.split("ARG<")[1:]]
        self.assertNotIn("No such file", out)
        self.assertEqual(args[:11], ["cron", "create", "--name", "yta-scan", "--monitor-script", "yta_poll.py",
                                     "--workdir", str(home), "--deliver", "telegram", "every 1m"])
        self.assertEqual(len(args), 12)
        self.assertIn("yta_escalations.py add", create)
        self.assertIn("[SILENT]", create)


if __name__ == "__main__":
    unittest.main()
