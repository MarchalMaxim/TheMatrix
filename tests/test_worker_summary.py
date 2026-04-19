import unittest

from server import summarize_notes


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


if __name__ == "__main__":
    unittest.main()
