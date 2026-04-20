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
# Fallback: catch malformed url() with unbalanced/missing quotes where the primary
# regex fails to match.  Rejects anything whose url argument starts with an
# absolute or protocol-relative scheme that is not data:image/.
CSS_URL_DANGEROUS_BARE = re.compile(
    r"url\(\s*['\"]?(?:https?:|//|ftp:|vbscript:|javascript:)",
    re.IGNORECASE,
)


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
    # Primary check: well-formed url() tokens.
    for match in CSS_URL_RE.finditer(css):
        target = match.group(2).strip()
        if target.startswith("#"):
            continue
        if target.lower().startswith("data:image/"):
            continue
        return False, "", f"css url() points to disallowed target: {target}"
    # Fallback: catch malformed url() with unbalanced quotes that the primary
    # regex misses (e.g. url("https://evil.com/) with no closing quote).
    if CSS_URL_DANGEROUS_BARE.search(css):
        return False, "", "css url() points to disallowed target (unbalanced)"
    return True, css, ""


import json as _json
import shutil
from dataclasses import dataclass
from pathlib import Path

import storage

GENERATED_DIR = storage.GENERATED_DIR
LAST_GOOD_DIR = storage.LAST_GOOD_DIR


@dataclass
class ApplyResult:
    applied: bool
    reason: str = ""


def apply_artifact(artifact: dict) -> ApplyResult:
    generated_dir: Path = GENERATED_DIR
    last_good_dir: Path = LAST_GOOD_DIR
    generated_dir.mkdir(parents=True, exist_ok=True)
    last_good_dir.mkdir(parents=True, exist_ok=True)

    theme_css = artifact.get("theme_css", "")
    slots = artifact.get("slots", {})

    # Empty artifact (chaos-deploy flow: the deploy workflow applied the
    # changes directly via git, there's nothing for us to lint or write).
    if not theme_css and not slots:
        return ApplyResult(True, "")

    css_ok, css_clean, css_reason = sanitise_css(theme_css)
    if not css_ok:
        return ApplyResult(False, css_reason)

    cleaned_slots: dict[str, str] = {}
    for name, html in slots.items():
        ok, clean, reason = sanitise_html(html)
        if not ok:
            return ApplyResult(False, f"slot '{name}': {reason}")
        cleaned_slots[name] = clean

    theme_path = generated_dir / "theme.css"
    slots_path = generated_dir / "slots.json"
    theme_path.write_text(css_clean, encoding="utf-8")
    slots_path.write_text(_json.dumps(cleaned_slots, indent=2), encoding="utf-8")

    # update last-good
    shutil.copy2(theme_path, last_good_dir / "theme.css")
    shutil.copy2(slots_path, last_good_dir / "slots.json")

    return ApplyResult(True)


def restore_last_good() -> bool:
    src_css = LAST_GOOD_DIR / "theme.css"
    src_slots = LAST_GOOD_DIR / "slots.json"
    if not src_css.exists() or not src_slots.exists():
        return False
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src_css, GENERATED_DIR / "theme.css")
    shutil.copy2(src_slots, GENERATED_DIR / "slots.json")
    return True
