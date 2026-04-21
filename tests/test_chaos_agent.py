"""Unit tests for scripts/run_chaos_agent.py tool implementations.

The actual Anthropic API call is not exercised here. Instead we patch
REPO_ROOT and PUBLIC_DIR to a tmp tree and verify the tools honour the
path-safety contract and the write-only-under-public/ rule."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

# Load the chaos agent module
SPEC = importlib.util.spec_from_file_location(
    "run_chaos_agent",
    Path(__file__).parent.parent / "scripts" / "run_chaos_agent.py",
)
chaos = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(chaos)


class _TempRepo:
    """Sets up REPO_ROOT/PUBLIC_DIR in a tmpdir for isolated tool tests."""

    def __enter__(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.public = self.root / "public"
        self.public.mkdir()
        (self.public / "index.html").write_text("<html></html>", encoding="utf-8")
        (self.public / "app.js").write_text("// app\n", encoding="utf-8")
        (self.public / "styles.css").write_text("body {}", encoding="utf-8")
        (self.public / "pow-worker.js").write_text("// worker\n", encoding="utf-8")
        (self.public / "scratch.txt").write_text("scratch", encoding="utf-8")
        self._patches = [
            mock.patch.object(chaos, "REPO_ROOT", self.root),
            mock.patch.object(chaos, "PUBLIC_DIR", self.public),
        ]
        for p in self._patches:
            p.start()
        return self

    def __exit__(self, *a):
        for p in self._patches:
            p.stop()
        self.tmp.cleanup()


class ListFilesTests(unittest.TestCase):
    def test_lists_public_by_default(self):
        with _TempRepo():
            res = chaos.tool_list_files()
        self.assertIn("files", res)
        self.assertIn("public/index.html", res["files"])
        self.assertEqual(res["count"], 5)

    def test_lists_subdirectory(self):
        with _TempRepo() as r:
            (r.public / "cycles").mkdir()
            (r.public / "cycles" / "x.json").write_text("{}")
            res = chaos.tool_list_files("public/cycles")
        self.assertEqual(res["files"], ["public/cycles/x.json"])

    def test_refuses_path_traversal(self):
        with _TempRepo():
            res = chaos.tool_list_files("public/../..")
        self.assertIn("error", res)

    def test_refuses_nonexistent(self):
        with _TempRepo():
            res = chaos.tool_list_files("nope")
        self.assertIn("error", res)


class ReadFileTests(unittest.TestCase):
    def test_reads_existing(self):
        with _TempRepo():
            res = chaos.tool_read_file("public/index.html")
        self.assertEqual(res["content"], "<html></html>")

    def test_refuses_traversal(self):
        with _TempRepo():
            res = chaos.tool_read_file("../outside")
        self.assertIn("error", res)

    def test_refuses_missing(self):
        with _TempRepo():
            res = chaos.tool_read_file("public/nope.txt")
        self.assertIn("error", res)

    def test_refuses_oversized(self):
        with _TempRepo() as r:
            big = "x" * (chaos.MAX_FILE_READ_BYTES + 10)
            (r.public / "big.txt").write_text(big)
            res = chaos.tool_read_file("public/big.txt")
        self.assertIn("error", res)
        self.assertIn("too large", res["error"])


class WriteFileTests(unittest.TestCase):
    def test_writes_under_public(self):
        with _TempRepo() as r:
            res = chaos.tool_write_file("public/new.html", "hi")
            self.assertTrue(res.get("ok"))
            self.assertEqual((r.public / "new.html").read_text(), "hi")

    def test_creates_parent_dirs(self):
        with _TempRepo() as r:
            res = chaos.tool_write_file("public/sub/deep/file.txt", "ok")
            self.assertTrue(res.get("ok"))
            self.assertTrue((r.public / "sub" / "deep" / "file.txt").is_file())

    def test_overwrites_existing(self):
        with _TempRepo() as r:
            chaos.tool_write_file("public/app.js", "new content")
            self.assertEqual((r.public / "app.js").read_text(), "new content")

    def test_refuses_outside_public(self):
        with _TempRepo() as r:
            res = chaos.tool_write_file("scripts/evil.py", "bad")
            self.assertIn("error", res)
            self.assertFalse((r.root / "scripts" / "evil.py").exists())

    def test_refuses_traversal(self):
        with _TempRepo():
            res = chaos.tool_write_file("public/../escape.txt", "x")
            self.assertIn("error", res)


class DeleteFileTests(unittest.TestCase):
    def test_deletes_non_core_file(self):
        with _TempRepo() as r:
            res = chaos.tool_delete_file("public/scratch.txt")
            self.assertTrue(res.get("ok"))
            self.assertFalse((r.public / "scratch.txt").exists())

    def test_refuses_core_file(self):
        with _TempRepo() as r:
            res = chaos.tool_delete_file("public/index.html")
            self.assertIn("error", res)
            self.assertTrue((r.public / "index.html").exists())

    def test_refuses_outside_public(self):
        with _TempRepo() as r:
            (r.root / "server.py").write_text("# server")
            res = chaos.tool_delete_file("server.py")
            self.assertIn("error", res)
            self.assertTrue((r.root / "server.py").exists())

    def test_refuses_missing(self):
        with _TempRepo():
            res = chaos.tool_delete_file("public/nope.txt")
            self.assertIn("error", res)


class DispatchTests(unittest.TestCase):
    def test_finalize_returns_ok(self):
        written: set = set()
        deleted: set = set()
        res = chaos.dispatch_tool("finalize", {"summary": "done"}, written, deleted)
        self.assertEqual(res, {"ok": True})

    def test_write_tracks_in_set(self):
        with _TempRepo():
            written: set = set()
            deleted: set = set()
            chaos.dispatch_tool("write_file",
                                {"path": "public/hi.txt", "content": "x"},
                                written, deleted)
            self.assertEqual(written, {"public/hi.txt"})

    def test_delete_removes_from_written_set(self):
        with _TempRepo() as r:
            (r.public / "tmp.txt").write_text("y")
            written: set = {"public/tmp.txt"}
            deleted: set = set()
            chaos.dispatch_tool("delete_file", {"path": "public/tmp.txt"},
                                written, deleted)
            self.assertEqual(written, set())
            self.assertEqual(deleted, {"public/tmp.txt"})

    def test_unknown_tool_returns_error(self):
        written: set = set()
        deleted: set = set()
        res = chaos.dispatch_tool("make_coffee", {}, written, deleted)
        self.assertIn("error", res)

    def test_missing_required_arg_returns_error(self):
        written: set = set()
        deleted: set = set()
        # read_file requires 'path'
        res = chaos.dispatch_tool("read_file", {}, written, deleted)
        self.assertIn("error", res)


class GetCycleHistoryTests(unittest.TestCase):
    def test_returns_empty_when_no_cycles_dir(self):
        with _TempRepo():
            res = chaos.tool_get_cycle_history()
        self.assertEqual(res["cycles"], [])

    def test_returns_cycles_newest_first(self):
        with _TempRepo() as r:
            cycles = r.public / "cycles"
            cycles.mkdir()
            # Oldest
            (cycles / "aaa.json").write_text(json.dumps({
                "handoff_id": "aaa",
                "summary": "first cycle",
                "agent_summary": "made it pink",
                "notes": [{"text": "hi"}],
                "files_written": ["public/styles.css"],
            }))
            import os as _os, time as _time
            _os.utime(cycles / "aaa.json", (_time.time() - 3600, _time.time() - 3600))
            # Newest
            (cycles / "bbb.json").write_text(json.dumps({
                "handoff_id": "bbb",
                "summary": "second cycle",
                "agent_summary": "made it green",
                "notes": [],
                "files_written": [],
            }))
            res = chaos.tool_get_cycle_history()
        self.assertEqual(len(res["cycles"]), 2)
        self.assertEqual(res["cycles"][0]["handoff_id"], "bbb")
        self.assertEqual(res["cycles"][1]["handoff_id"], "aaa")

    def test_honours_limit(self):
        with _TempRepo() as r:
            cycles = r.public / "cycles"
            cycles.mkdir()
            for i in range(5):
                (cycles / f"c{i}.json").write_text(json.dumps({
                    "handoff_id": f"c{i}",
                    "summary": f"cycle {i}",
                    "notes": [],
                }))
            res = chaos.tool_get_cycle_history(limit=2)
        self.assertEqual(len(res["cycles"]), 2)

    def test_clamps_out_of_range_limit(self):
        with _TempRepo() as r:
            cycles = r.public / "cycles"
            cycles.mkdir()
            res = chaos.tool_get_cycle_history(limit=1000)
        # Accepts but clamps; 0 files gives 0 results, not an error
        self.assertEqual(res["cycles"], [])

    def test_skips_malformed_json(self):
        with _TempRepo() as r:
            cycles = r.public / "cycles"
            cycles.mkdir()
            (cycles / "good.json").write_text(json.dumps({"handoff_id": "good"}))
            (cycles / "bad.json").write_text("{ not json")
            res = chaos.tool_get_cycle_history()
        ids = [c["handoff_id"] for c in res["cycles"]]
        self.assertIn("good", ids)
        self.assertNotIn("bad", ids)


class FetchUrlTests(unittest.TestCase):
    def test_refuses_non_http(self):
        res = chaos.tool_fetch_url("ftp://example.com/x")
        self.assertIn("error", res)

    def test_refuses_localhost(self):
        res = chaos.tool_fetch_url("http://localhost:8000/foo")
        self.assertIn("error", res)
        self.assertIn("block", res["error"])

    def test_refuses_loopback_ip(self):
        res = chaos.tool_fetch_url("http://127.0.0.1/foo")
        self.assertIn("error", res)

    def test_refuses_private_ip(self):
        res = chaos.tool_fetch_url("http://10.0.0.5/foo")
        self.assertIn("error", res)

    def test_refuses_link_local(self):
        res = chaos.tool_fetch_url("http://169.254.169.254/latest/meta-data/")
        self.assertIn("error", res)

    def test_refuses_metadata_hostname(self):
        res = chaos.tool_fetch_url("http://metadata.google.internal/x")
        self.assertIn("error", res)

    def test_fetches_success(self):
        """Happy path with urlopen patched to return small text body."""
        class _FakeResp:
            headers = {"Content-Type": "text/css"}
            def read(self, n=None):
                return b"body { color: red }"
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with mock.patch.object(chaos.urllib.request, "urlopen",
                               return_value=_FakeResp()):
            res = chaos.tool_fetch_url("https://example.com/foo.css")
        self.assertEqual(res["content"], "body { color: red }")
        self.assertEqual(res["content_type"], "text/css")
        self.assertFalse(res["truncated"])

    def test_truncates_oversized(self):
        class _FakeResp:
            headers = {"Content-Type": "text/html"}
            def read(self, n=None):
                # Return max+1 bytes so the tool marks it truncated
                return b"x" * (chaos.FETCH_URL_MAX_BYTES + 1)
            def __enter__(self): return self
            def __exit__(self, *a): pass

        with mock.patch.object(chaos.urllib.request, "urlopen",
                               return_value=_FakeResp()):
            res = chaos.tool_fetch_url("https://example.com/big")
        self.assertTrue(res["truncated"])
        self.assertEqual(len(res["content"]), chaos.FETCH_URL_MAX_BYTES)

    def test_handles_http_error(self):
        import io as _io
        err = chaos.urllib.error.HTTPError(
            "https://x", 404, "Not Found", {}, _io.BytesIO(b""))
        with mock.patch.object(chaos.urllib.request, "urlopen", side_effect=err):
            res = chaos.tool_fetch_url("https://example.com/missing")
        self.assertIn("error", res)
        self.assertIn("404", res["error"])

    def test_handles_network_error(self):
        err = chaos.urllib.error.URLError("DNS fail")
        with mock.patch.object(chaos.urllib.request, "urlopen", side_effect=err):
            res = chaos.tool_fetch_url("https://doesnotexist.example.com/")
        self.assertIn("error", res)


class WallClockBudgetTests(unittest.TestCase):
    """The agent must stop calling the API once it's used up its wall-clock
    budget, so the workflow's commit step still has time to salvage partial
    work."""

    @staticmethod
    def _fake_time_module(sequence):
        """Return an object mimicking `time` with a scripted monotonic()."""
        import types
        it = iter(sequence)
        return types.SimpleNamespace(monotonic=lambda: next(it))

    def test_budget_hit_breaks_loop_before_first_turn(self):
        # Script monotonic so t=0 at start, t=999 on first in-loop check.
        # With budget=10s, loop breaks without any API call.
        fake_time = self._fake_time_module([0.0, 999.0])
        with mock.patch.object(chaos, "anthropic_call") as fake_call, \
             mock.patch.object(chaos, "WALL_CLOCK_BUDGET_SECONDS", 10), \
             mock.patch.dict("sys.modules", {"time": fake_time}):
            outcome = chaos.run_agent_loop("summary", [])
        self.assertFalse(fake_call.called)
        self.assertTrue(outcome["budget_hit"])
        self.assertFalse(outcome["finalized"])
        self.assertEqual(outcome["written"], [])

    def test_budget_hit_after_partial_work_preserves_writes(self):
        """Simulate: agent writes 2 files across 2 turns, then budget hits."""
        with _TempRepo():
            call_count = {"n": 0}

            def fake_call(messages):
                call_count["n"] += 1
                n = call_count["n"]
                return {
                    "content": [
                        {
                            "type": "tool_use",
                            "id": f"tu_{n}",
                            "name": "write_file",
                            "input": {"path": f"public/new{n}.html", "content": f"<p>{n}</p>"},
                        }
                    ]
                }

            # monotonic sequence: start=0, check-turn0=1, check-turn1=2,
            # check-turn2=999 (budget breaks loop). Budget=10s.
            fake_time = self._fake_time_module([0.0, 1.0, 2.0, 999.0])
            with mock.patch.object(chaos, "anthropic_call", side_effect=fake_call), \
                 mock.patch.object(chaos, "WALL_CLOCK_BUDGET_SECONDS", 10), \
                 mock.patch.dict("sys.modules", {"time": fake_time}):
                outcome = chaos.run_agent_loop("summary", [])
        # 2 writes succeeded before the budget killed turn 3
        self.assertTrue(outcome["budget_hit"])
        self.assertEqual(len(outcome["written"]), 2)
        self.assertFalse(outcome["finalized"])


class BuildInitialMessageTests(unittest.TestCase):
    def test_includes_summary_and_notes(self):
        msg = chaos.build_initial_message(
            "make it scream",
            [{"text": "add fire", "votes": 3},
             {"text": "make it louder", "votes": 1}],
        )
        self.assertIn("make it scream", msg)
        self.assertIn("add fire", msg)
        self.assertIn("(3 votes)", msg)

    def test_empty_notes_fallback(self):
        msg = chaos.build_initial_message("x", [])
        self.assertIn("no user prompts", msg)


if __name__ == "__main__":
    unittest.main()
