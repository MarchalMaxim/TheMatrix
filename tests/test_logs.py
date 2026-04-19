import unittest

import logs


class LogsTests(unittest.TestCase):
    def setUp(self):
        logs.reset_for_tests()

    def test_log_records_include_level_and_message(self):
        logs.log("info", "hello world")
        records = logs.recent()
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["level"], "info")
        self.assertEqual(records[0]["message"], "hello world")
        self.assertIn("ts", records[0])

    def test_buffer_holds_at_most_capacity(self):
        for i in range(logs.CAPACITY + 50):
            logs.log("info", f"msg-{i}")
        records = logs.recent()
        self.assertEqual(len(records), logs.CAPACITY)
        self.assertEqual(records[-1]["message"], f"msg-{logs.CAPACITY + 49}")

    def test_recent_returns_newest_last(self):
        logs.log("info", "first")
        logs.log("warn", "second")
        records = logs.recent()
        self.assertEqual(records[0]["message"], "first")
        self.assertEqual(records[1]["message"], "second")

    def test_log_accepts_structured_fields(self):
        logs.log("info", "with extras", run_id="r1", count=3)
        records = logs.recent()
        self.assertEqual(records[0]["run_id"], "r1")
        self.assertEqual(records[0]["count"], 3)


if __name__ == "__main__":
    unittest.main()
