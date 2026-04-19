import unittest

import lint


class HtmlLintTests(unittest.TestCase):
    def test_allows_basic_tags(self):
        ok, cleaned, _ = lint.sanitise_html("<p>Hello <strong>world</strong></p>")
        self.assertTrue(ok)
        self.assertIn("<p>", cleaned)
        self.assertIn("<strong>", cleaned)

    def test_strips_script_tag(self):
        ok, _, reason = lint.sanitise_html("<p>ok</p><script>alert(1)</script>")
        self.assertFalse(ok)
        self.assertIn("script", reason)

    def test_strips_event_handlers(self):
        ok, _, reason = lint.sanitise_html('<p onclick="x()">hi</p>')
        self.assertFalse(ok)
        self.assertIn("on", reason.lower())

    def test_strips_iframe(self):
        ok, _, reason = lint.sanitise_html("<iframe src='evil'></iframe>")
        self.assertFalse(ok)
        self.assertIn("iframe", reason)

    def test_allows_anchor_with_hash(self):
        ok, cleaned, _ = lint.sanitise_html('<a href="#top">top</a>')
        self.assertTrue(ok)
        self.assertIn('href="#top"', cleaned)

    def test_rejects_anchor_with_external_href(self):
        ok, _, reason = lint.sanitise_html('<a href="https://evil.com">click</a>')
        self.assertFalse(ok)
        self.assertIn("href", reason)

    def test_too_large_rejected(self):
        ok, _, reason = lint.sanitise_html("<p>" + ("x" * 60_000) + "</p>")
        self.assertFalse(ok)
        self.assertIn("large", reason)


class CssLintTests(unittest.TestCase):
    def test_allows_basic_css(self):
        ok, _, _ = lint.sanitise_css("body { background: pink; color: #333; }")
        self.assertTrue(ok)

    def test_rejects_at_import(self):
        ok, _, reason = lint.sanitise_css("@import url('//evil.com/a.css');")
        self.assertFalse(ok)
        self.assertIn("import", reason.lower())

    def test_rejects_external_url(self):
        ok, _, reason = lint.sanitise_css("body { background: url(https://evil.com/x.png); }")
        self.assertFalse(ok)
        self.assertIn("url", reason.lower())

    def test_allows_data_image_url(self):
        ok, _, _ = lint.sanitise_css("body { background: url(data:image/png;base64,iVBORw0KGgo=); }")
        self.assertTrue(ok)

    def test_rejects_expression(self):
        ok, _, reason = lint.sanitise_css("p { width: expression(alert(1)); }")
        self.assertFalse(ok)
        self.assertIn("expression", reason.lower())

    def test_rejects_javascript_protocol(self):
        ok, _, reason = lint.sanitise_css("p { background: url('javascript:alert(1)'); }")
        self.assertFalse(ok)
        self.assertTrue(reason)

    def test_too_large_rejected(self):
        ok, _, reason = lint.sanitise_css("body{}" + ("a{}" * 20_000))
        self.assertFalse(ok)
        self.assertIn("large", reason)

    def test_rejects_url_unbalanced_double_quote(self):
        # url("https://evil.com/) — closing quote missing; primary regex misses it
        ok, _, reason = lint.sanitise_css('body{background:url("https://evil.com/evil.png)}')
        self.assertFalse(ok)

    def test_rejects_url_unbalanced_single_quote(self):
        ok, _, reason = lint.sanitise_css("body{background:url('https://evil.com/evil.png)}")
        self.assertFalse(ok)

    def test_rejects_protocol_relative_url(self):
        ok, _, reason = lint.sanitise_css("body{background:url(//evil.com/evil.png)}")
        self.assertFalse(ok)


import json
import shutil
import tempfile
from pathlib import Path
from unittest import mock


class ApplyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.gen = Path(self.tmp.name) / "generated"
        self.last_good = self.gen / ".last_good"
        self.gen.mkdir(parents=True)
        self.last_good.mkdir()
        patcher_gen = mock.patch.object(lint, "GENERATED_DIR", self.gen)
        patcher_lg = mock.patch.object(lint, "LAST_GOOD_DIR", self.last_good)
        patcher_gen.start()
        patcher_lg.start()
        self.addCleanup(patcher_gen.stop)
        self.addCleanup(patcher_lg.stop)
        self.addCleanup(self.tmp.cleanup)

    def test_apply_writes_theme_and_slots(self):
        result = lint.apply_artifact({
            "theme_css": "body { background: pink; }",
            "slots": {"intro": "<p>hi</p>"},
        })
        self.assertTrue(result.applied)
        self.assertEqual(
            (self.gen / "theme.css").read_text(encoding="utf-8"),
            "body { background: pink; }",
        )
        self.assertEqual(
            json.loads((self.gen / "slots.json").read_text(encoding="utf-8")),
            {"intro": "<p>hi</p>"},
        )

    def test_apply_rejects_bad_css_and_keeps_last_good(self):
        # seed last_good with a known artifact
        (self.last_good / "theme.css").write_text("body { background: lime; }")
        (self.last_good / "slots.json").write_text(json.dumps({"intro": "<p>old</p>"}))
        # also seed live so we can confirm replacement
        (self.gen / "theme.css").write_text("body { background: lime; }")
        (self.gen / "slots.json").write_text(json.dumps({"intro": "<p>old</p>"}))

        result = lint.apply_artifact({
            "theme_css": "@import url('//evil.com/a.css');",
            "slots": {"intro": "<p>ok</p>"},
        })
        self.assertFalse(result.applied)
        self.assertIn("import", result.reason.lower())
        self.assertEqual(
            (self.gen / "theme.css").read_text(encoding="utf-8"),
            "body { background: lime; }",
        )

    def test_apply_rejects_bad_slot_html(self):
        result = lint.apply_artifact({
            "theme_css": "body { background: pink; }",
            "slots": {"intro": "<script>alert(1)</script>"},
        })
        self.assertFalse(result.applied)
        self.assertIn("script", result.reason.lower())

    def test_successful_apply_updates_last_good(self):
        lint.apply_artifact({
            "theme_css": "body { color: red; }",
            "slots": {"intro": "<p>v1</p>"},
        })
        lint.apply_artifact({
            "theme_css": "body { color: blue; }",
            "slots": {"intro": "<p>v2</p>"},
        })
        self.assertEqual(
            (self.last_good / "theme.css").read_text(encoding="utf-8"),
            "body { color: blue; }",
        )


if __name__ == "__main__":
    unittest.main()
