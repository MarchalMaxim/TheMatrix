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


if __name__ == "__main__":
    unittest.main()
