import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patcher = mock.patch.object(storage, "DATA_DIR", self.root / "data")
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_read_json_returns_default_when_missing(self):
        result = storage.read_json(Path("does/not/exist.json"), default=[])
        self.assertEqual(result, [])

    def test_write_then_read_roundtrips(self):
        path = self.root / "data" / "thing.json"
        storage.write_json(path, {"a": 1, "b": [2, 3]})
        self.assertEqual(storage.read_json(path, default={}), {"a": 1, "b": [2, 3]})

    def test_write_creates_parent_dirs(self):
        path = self.root / "data" / "nested" / "deep" / "file.json"
        storage.write_json(path, [1, 2])
        self.assertTrue(path.exists())

    def test_with_lock_serialises_writes(self):
        path = self.root / "data" / "counter.json"
        storage.write_json(path, {"n": 0})

        def increment():
            with storage.with_lock(path):
                data = storage.read_json(path, default={"n": 0})
                data["n"] += 1
                storage.write_json(path, data)

        import threading
        threads = [threading.Thread(target=increment) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(storage.read_json(path, default={"n": 0})["n"], 20)


class SaltTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.patcher = mock.patch.object(storage, "DATA_DIR", self.root / "data")
        self.patcher.start()
        self.salt_patcher = mock.patch.object(
            storage, "SALT_PATH", self.root / "data" / "salt.json"
        )
        self.salt_patcher.start()
        self.addCleanup(self.patcher.stop)
        self.addCleanup(self.salt_patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_get_daily_salt_creates_one_when_missing(self):
        salt = storage.get_daily_salt(today="2026-04-19")
        self.assertEqual(len(salt), 32)
        again = storage.get_daily_salt(today="2026-04-19")
        self.assertEqual(salt, again)

    def test_get_daily_salt_rotates_per_day(self):
        a = storage.get_daily_salt(today="2026-04-19")
        b = storage.get_daily_salt(today="2026-04-20")
        self.assertNotEqual(a, b)


if __name__ == "__main__":
    unittest.main()
