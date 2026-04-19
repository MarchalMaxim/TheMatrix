import unittest
import time

from server import WORKER_STATE, WORKER_STATE_LOCK, get_worker_status, summarize_notes


class SummaryTests(unittest.TestCase):
    def test_empty_notes(self):
        result = summarize_notes([])
        self.assertEqual(result["suggestions_count"], 0)
        self.assertEqual(result["top_topics"], [])

    def test_topics_are_extracted(self):
        notes = [
            {"text": "Please add dark mode and keyboard shortcuts"},
            {"text": "Dark mode plus better shortcut help"},
        ]
        result = summarize_notes(notes)
        self.assertEqual(result["suggestions_count"], 2)
        self.assertIn("dark", result["top_topics"])
        self.assertIn("mode", result["top_topics"])
        self.assertNotIn("please", result["top_topics"])
        self.assertNotIn("and", result["top_topics"])
        self.assertIn("Collected 2 suggestion", result["summary"])

    def test_worker_status_countdown_and_summary(self):
        with WORKER_STATE_LOCK:
            WORKER_STATE["summary"] = "Collected 3 suggestion(s)."
            WORKER_STATE["top_topics"] = ["clock", "generation"]
            WORKER_STATE["suggestions_count"] = 3
            WORKER_STATE["last_run_utc"] = "2026-04-19T19:00:00+00:00"
            WORKER_STATE["next_run_epoch"] = time.time() + 25

        status = get_worker_status()
        self.assertEqual(status["summary"], "Collected 3 suggestion(s).")
        self.assertEqual(status["suggestions_count"], 3)
        self.assertIn("clock", status["top_topics"])
        self.assertGreaterEqual(status["seconds_until_next_cycle"], 0)


if __name__ == "__main__":
    unittest.main()
