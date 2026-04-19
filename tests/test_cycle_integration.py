import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import storage
import abuse
import lint


class CyclePipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patches = [
            mock.patch.object(storage, "DATA_DIR", self.root / "data"),
            mock.patch.object(storage, "WORKER_DIR", self.root / "worker" / "copilot_handoff"),
            mock.patch.object(storage, "NOTES_PATH", self.root / "data" / "notes.json"),
            mock.patch.object(storage, "CYCLES_DIR", self.root / "data" / "cycles"),
            mock.patch.object(storage, "RUNS_PATH", self.root / "data" / "runs.json"),
            mock.patch.object(storage, "SALT_PATH", self.root / "data" / "salt.json"),
            mock.patch.object(storage, "CURRENT_CYCLE_PATH", self.root / "data" / "current_cycle.json"),
            mock.patch.object(storage, "GENERATED_DIR", self.root / "public" / "generated"),
            mock.patch.object(storage, "LAST_GOOD_DIR", self.root / "public" / "generated" / ".last_good"),
            mock.patch.object(lint, "GENERATED_DIR", self.root / "public" / "generated"),
            mock.patch.object(lint, "LAST_GOOD_DIR", self.root / "public" / "generated" / ".last_good"),
        ]
        for p in self.patches:
            p.start()
        storage.ensure_dirs()
        storage.NOTES_PATH.write_text("[]")
        self.addCleanup(self.tmp.cleanup)
        for p in self.patches:
            self.addCleanup(p.stop)

        import server
        import agent as _agent
        self.server = server
        server.NOTES_PATH = storage.NOTES_PATH
        server.AGENT = _agent.MockGithubAgent(queued_seconds=0.01, running_seconds=0.01)
        abuse.reset_quota_for_tests()

    def test_close_cycle_records_failure_when_kick_off_raises(self):
        import agent as _agent

        class FailingAgent:
            is_mock = True
            def kick_off(self, handoff):
                raise _agent.AgentError("simulated kick_off failure")
            def poll(self, run_id):
                raise _agent.AgentError("nope")
            def fetch_artifact(self, run_id):
                raise _agent.AgentError("nope")

        self.server.AGENT = FailingAgent()
        storage.write_json(storage.NOTES_PATH, [
            {"id": "a", "text": "hi", "x": 0, "y": 0, "color": "#fff",
             "createdAt": "x", "votes": 1, "voter_hashes": [], "submitter_hash": "h", "cycle_id": "c1"},
        ])
        storage.write_json(storage.CURRENT_CYCLE_PATH, {"cycle_id": "c1", "started_at": "x", "ends_at": None})

        run_id = self.server.close_cycle()
        runs = storage.read_json(storage.RUNS_PATH, default=[])
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["status"], "failed")
        self.assertIn("simulated", runs[0]["error"])
        # cycle still archived + new cycle opened
        self.assertIsNotNone(storage.read_json(storage.CYCLES_DIR / "c1.json", default=None))
        new_cycle = storage.read_json(storage.CURRENT_CYCLE_PATH, default={})
        self.assertNotEqual(new_cycle["cycle_id"], "c1")

    def test_close_cycle_archives_notes_and_kicks_off_run(self):
        # seed notes
        storage.write_json(storage.NOTES_PATH, [
            {"id": "a", "text": "make it pink", "x": 0, "y": 0, "color": "#fff",
             "createdAt": "x", "votes": 5, "voter_hashes": [], "submitter_hash": "h", "cycle_id": "c1"},
            {"id": "b", "text": "make it green", "x": 0, "y": 0, "color": "#fff",
             "createdAt": "y", "votes": 1, "voter_hashes": [], "submitter_hash": "h", "cycle_id": "c1"},
        ])
        storage.write_json(storage.CURRENT_CYCLE_PATH, {"cycle_id": "c1", "started_at": "x", "ends_at": "y"})

        run_id = self.server.close_cycle()

        # archive
        archive = storage.read_json(storage.CYCLES_DIR / "c1.json", default=None)
        self.assertIsNotNone(archive)
        self.assertEqual(archive["cycle_id"], "c1")
        self.assertEqual(len(archive["top_notes"]), 2)
        self.assertEqual(archive["top_notes"][0]["id"], "a")  # higher votes first
        self.assertEqual(archive["run_id"], run_id)

        # notes cleared, new cycle opened
        self.assertEqual(storage.read_json(storage.NOTES_PATH, default=None), [])
        new_cycle = storage.read_json(storage.CURRENT_CYCLE_PATH, default={})
        self.assertNotEqual(new_cycle["cycle_id"], "c1")

        # runs.json got a new entry
        runs = storage.read_json(storage.RUNS_PATH, default=[])
        self.assertEqual(len(runs), 1)
        self.assertEqual(runs[0]["run_id"], run_id)
        self.assertEqual(runs[0]["status"], "queued")
        self.assertEqual(runs[0]["cycle_id"], "c1")


import time as _time


class PollerTests(CyclePipelineTests):
    def test_poller_advances_run_to_applied_after_merge(self):
        storage.write_json(storage.NOTES_PATH, [
            {"id": "a", "text": "make it pink", "x": 0, "y": 0, "color": "#fff",
             "createdAt": "x", "votes": 5, "voter_hashes": [], "submitter_hash": "h", "cycle_id": "c1"},
        ])
        storage.write_json(storage.CURRENT_CYCLE_PATH, {"cycle_id": "c1", "started_at": "x", "ends_at": None})
        run_id = self.server.close_cycle()

        # tick poller once → status becomes queued (no change yet)
        self.server.poll_runs_once()
        runs = storage.read_json(storage.RUNS_PATH, default=[])
        self.assertEqual(runs[0]["status"], "queued")

        # advance mock past queued+running
        _time.sleep(0.05)
        self.server.poll_runs_once()
        runs = storage.read_json(storage.RUNS_PATH, default=[])
        self.assertEqual(runs[0]["status"], "needs_merge")

        # operator merges
        self.server.AGENT.signal_merge(run_id)
        self.server.poll_runs_once()
        runs = storage.read_json(storage.RUNS_PATH, default=[])
        self.assertEqual(runs[0]["status"], "applied")

        # generated artifacts written
        self.assertTrue((storage.GENERATED_DIR / "theme.css").exists())
        self.assertTrue((storage.GENERATED_DIR / "slots.json").exists())
