import json
import threading
import time
import unittest
import urllib.request
import urllib.error
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import storage
import abuse


def _start_server(tmp_root: Path):
    # Patch storage paths into tmp_root
    patches = [
        mock.patch.object(storage, "DATA_DIR", tmp_root / "data"),
        mock.patch.object(storage, "WORKER_DIR", tmp_root / "worker" / "copilot_handoff"),
        mock.patch.object(storage, "NOTES_PATH", tmp_root / "data" / "notes.json"),
        mock.patch.object(storage, "CYCLES_DIR", tmp_root / "data" / "cycles"),
        mock.patch.object(storage, "RUNS_PATH", tmp_root / "data" / "runs.json"),
        mock.patch.object(storage, "SALT_PATH", tmp_root / "data" / "salt.json"),
        mock.patch.object(storage, "CURRENT_CYCLE_PATH", tmp_root / "data" / "current_cycle.json"),
        mock.patch.object(storage, "GENERATED_DIR", tmp_root / "public" / "generated"),
        mock.patch.object(storage, "LAST_GOOD_DIR", tmp_root / "public" / "generated" / ".last_good"),
    ]
    for p in patches:
        p.start()
    storage.ensure_dirs()
    storage.NOTES_PATH.write_text("[]", encoding="utf-8")

    import server  # imported after patching
    server.NOTES_PATH = storage.NOTES_PATH
    import agent as _agent
    server.AGENT = _agent.MockGithubAgent(queued_seconds=0.05, running_seconds=0.05)
    abuse.reset_quota_for_tests()

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.NoteBoardHandler)
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def stop():
        httpd.shutdown()
        for p in patches:
            p.stop()

    return f"http://127.0.0.1:{port}", stop


def _post(url, body, ua="test"):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": ua},
        method="POST",
    )
    return urllib.request.urlopen(req)


class VoteEndpointTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.url, self.stop = _start_server(Path(self.tmp.name))
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.stop)

    def _make_note(self):
        # bypass abuse for setup by writing directly
        notes = json.loads(storage.NOTES_PATH.read_text())
        notes.append({
            "id": "n1",
            "text": "hello",
            "x": 10, "y": 10, "color": "#fff",
            "createdAt": "2026-04-19T00:00:00+00:00",
            "votes": 0,
            "voter_hashes": [],
            "submitter_hash": "anon",
            "cycle_id": "cycle-test",
        })
        storage.NOTES_PATH.write_text(json.dumps(notes))
        storage.write_json(storage.CURRENT_CYCLE_PATH, {"cycle_id": "cycle-test", "started_at": "x", "ends_at": "y"})

    def _solve_pow(self, challenge, difficulty):
        import hashlib
        nonce = 0
        while True:
            digest = hashlib.sha256(f"{challenge}:{nonce}".encode("utf-8")).digest()
            count = 0
            for byte in digest:
                if byte == 0:
                    count += 8
                    continue
                for shift in range(7, -1, -1):
                    if (byte >> shift) & 1:
                        break
                    count += 1
                break
            if count >= difficulty:
                return str(nonce)
            nonce += 1

    def test_vote_increments_count(self):
        self._make_note()
        salt = storage.get_daily_salt(today="2026-04-19")
        voter = abuse.submitter_hash("127.0.0.1", "test", salt=salt)
        challenge = abuse.make_pow_challenge("cycle-test", voter)
        nonce = self._solve_pow(challenge, abuse.POW_DIFFICULTY_VOTE)
        resp = _post(f"{self.url}/api/notes/n1/vote", {"pow": nonce, "challenge": challenge})
        self.assertEqual(resp.status, 200)
        data = json.loads(resp.read())
        self.assertEqual(data["votes"], 1)

    def test_double_vote_unvotes(self):
        self._make_note()
        salt = storage.get_daily_salt(today="2026-04-19")
        voter = abuse.submitter_hash("127.0.0.1", "test", salt=salt)
        challenge = abuse.make_pow_challenge("cycle-test", voter)
        nonce = self._solve_pow(challenge, abuse.POW_DIFFICULTY_VOTE)
        _post(f"{self.url}/api/notes/n1/vote", {"pow": nonce, "challenge": challenge})
        resp = _post(f"{self.url}/api/notes/n1/vote", {"pow": nonce, "challenge": challenge})
        data = json.loads(resp.read())
        self.assertEqual(data["votes"], 0)

    def test_vote_rejects_bad_pow(self):
        self._make_note()
        try:
            _post(f"{self.url}/api/notes/n1/vote", {"pow": "0", "challenge": "x"})
            self.fail("expected 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)


if __name__ == "__main__":
    unittest.main()
