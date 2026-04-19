from __future__ import annotations

import hashlib
import re

MAX_NOTE_LENGTH = 500

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous", re.IGNORECASE),
    re.compile(r"system\s+prompt", re.IGNORECASE),
    re.compile(r"<\s*script", re.IGNORECASE),
    re.compile(r"</\s*script", re.IGNORECASE),
    re.compile(r"on\w+\s*=", re.IGNORECASE),
    re.compile(r"javascript:", re.IGNORECASE),
]


def submitter_hash(ip: str, user_agent: str, salt: str) -> str:
    payload = f"{ip}|{user_agent}|{salt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def lint_submission(text: str) -> tuple[bool, str]:
    stripped = text.strip()
    if not stripped:
        return False, "submission is empty"
    if len(stripped) > MAX_NOTE_LENGTH:
        return False, f"submission too long (>{MAX_NOTE_LENGTH} chars)"
    for pattern in INJECTION_PATTERNS:
        if pattern.search(stripped):
            return False, f"submission matched suspicious pattern: {pattern.pattern}"
    return True, ""
