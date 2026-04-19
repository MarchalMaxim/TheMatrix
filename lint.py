from __future__ import annotations

import re
from html.parser import HTMLParser

MAX_HTML_BYTES = 50_000
MAX_CSS_BYTES = 50_000

ALLOWED_TAGS = {
    "div", "span", "p",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li",
    "em", "strong", "br", "hr", "a",
    "blockquote", "code", "pre", "figure", "figcaption",
}
ALLOWED_ATTRS = {"class", "href"}

DANGEROUS_TAGS = {"script", "iframe", "object", "embed", "style", "link", "meta", "base"}

CSS_FORBIDDEN = [
    (re.compile(r"@import", re.IGNORECASE), "css contains @import"),
    (re.compile(r"expression\s*\(", re.IGNORECASE), "css contains expression()"),
    (re.compile(r"behavior\s*:", re.IGNORECASE), "css contains behavior property"),
    (re.compile(r"javascript:", re.IGNORECASE), "css contains javascript: protocol"),
]
CSS_URL_RE = re.compile(r"url\(\s*(['\"]?)([^'\")]+)\1\s*\)", re.IGNORECASE)


class _Sanitiser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.error: str | None = None

    def _fail(self, reason: str) -> None:
        if self.error is None:
            self.error = reason

    def handle_starttag(self, tag, attrs):
        self._handle_tag(tag, attrs, closing=False)

    def handle_startendtag(self, tag, attrs):
        self._handle_tag(tag, attrs, closing=True)

    def handle_endtag(self, tag):
        if tag in DANGEROUS_TAGS:
            self._fail(f"disallowed tag <{tag}>")
            return
        if tag not in ALLOWED_TAGS:
            self._fail(f"disallowed tag <{tag}>")
            return
        self.parts.append(f"</{tag}>")

    def handle_data(self, data):
        self.parts.append(data)

    def _handle_tag(self, tag, attrs, closing: bool) -> None:
        if tag in DANGEROUS_TAGS:
            self._fail(f"disallowed tag <{tag}>")
            return
        if tag not in ALLOWED_TAGS:
            self._fail(f"disallowed tag <{tag}>")
            return
        kept_attrs: list[str] = []
        for name, value in attrs:
            lname = name.lower()
            if lname.startswith("on"):
                self._fail(f"disallowed on* attribute: {lname}")
                return
            if lname not in ALLOWED_ATTRS:
                # silently drop unknown attrs
                continue
            if lname == "href":
                if value is None or not value.startswith("#"):
                    self._fail("href must start with #")
                    return
            escaped = (value or "").replace('"', "&quot;")
            kept_attrs.append(f'{lname}="{escaped}"')
        attrs_str = (" " + " ".join(kept_attrs)) if kept_attrs else ""
        end = "/" if closing else ""
        self.parts.append(f"<{tag}{attrs_str}{end}>")


def sanitise_html(html: str) -> tuple[bool, str, str]:
    if len(html.encode("utf-8")) > MAX_HTML_BYTES:
        return False, "", "html too large"
    parser = _Sanitiser()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:  # malformed input
        return False, "", f"html parse error: {exc}"
    if parser.error:
        return False, "", parser.error
    return True, "".join(parser.parts), ""


def sanitise_css(css: str) -> tuple[bool, str, str]:
    if len(css.encode("utf-8")) > MAX_CSS_BYTES:
        return False, "", "css too large"
    for pattern, reason in CSS_FORBIDDEN:
        if pattern.search(css):
            return False, "", reason
    for match in CSS_URL_RE.finditer(css):
        target = match.group(2).strip()
        if target.startswith("#"):
            continue
        if target.lower().startswith("data:image/"):
            continue
        return False, "", f"css url() points to disallowed target: {target}"
    return True, css, ""
