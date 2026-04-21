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
