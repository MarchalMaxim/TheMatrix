"""Tests for scripts/generate_artifact.py — parser + fallback paths only.
The actual Anthropic API call is not exercised here (network would be involved)."""
import importlib.util
import json
import sys
import unittest
from pathlib import Path

# Load the script as a module without making it importable as a package
SPEC = importlib.util.spec_from_file_location(
    "generate_artifact",
    Path(__file__).parent.parent / "scripts" / "generate_artifact.py",
)
generate_artifact = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(generate_artifact)


class ParseResponseTests(unittest.TestCase):
    def test_clean_response(self):
        text = (
            "body { background: red; }\n"
            "---SPLIT---\n"
            '{"intro":"<p>hi</p>","aside":"<p>x</p>","footer-extra":"<p>y</p>"}'
        )
        css, slots = generate_artifact.parse_response(text)
        self.assertIn("background: red", css)
        self.assertEqual(slots["intro"], "<p>hi</p>")

    def test_response_with_code_fences(self):
        text = (
            "```css\n"
            "body { color: blue; }\n"
            "```\n"
            "---SPLIT---\n"
            "```json\n"
            '{"intro":"a","aside":"b","footer-extra":"c"}\n'
            "```"
        )
        css, slots = generate_artifact.parse_response(text)
        self.assertIn("color: blue", css)
        self.assertNotIn("```", css)
        self.assertEqual(slots["intro"], "a")

    def test_missing_split_raises(self):
        with self.assertRaises(ValueError):
            generate_artifact.parse_response("just css, no split")

    def test_no_json_in_part2_raises(self):
        with self.assertRaises(ValueError):
            generate_artifact.parse_response("css\n---SPLIT---\nnot json at all")


class FallbackArtifactTests(unittest.TestCase):
    def test_fallback_is_deterministic_for_same_summary(self):
        css1, slots1 = generate_artifact.fallback_artifact("hello", [])
        css2, slots2 = generate_artifact.fallback_artifact("hello", [])
        self.assertEqual(css1, css2)
        self.assertEqual(slots1, slots2)

    def test_fallback_includes_first_note_text(self):
        _, slots = generate_artifact.fallback_artifact(
            "x", [{"text": "neon dragon mode"}, {"text": "y"}]
        )
        self.assertIn("neon dragon mode", slots["intro"])

    def test_fallback_returns_required_slot_keys(self):
        _, slots = generate_artifact.fallback_artifact("x", [])
        self.assertEqual(set(slots), {"intro", "aside", "footer-extra"})


if __name__ == "__main__":
    unittest.main()
