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


import time

POW_DIFFICULTY_SUBMIT = 18
POW_DIFFICULTY_VOTE = 14


def make_pow_challenge(cycle_id: str, submitter_hash_value: str, minute_bucket: int | None = None) -> str:
    if minute_bucket is None:
        minute_bucket = int(time.time() // 60)
    return f"{cycle_id}:{submitter_hash_value}:{minute_bucket}"


def _leading_zero_bits(digest: bytes) -> int:
    count = 0
    for byte in digest:
        if byte == 0:
            count += 8
            continue
        # count leading zero bits in this byte
        for shift in range(7, -1, -1):
            if (byte >> shift) & 1:
                return count
            count += 1
        return count
    return count


def verify_pow(challenge: str, nonce: str, difficulty_bits: int) -> bool:
    if not isinstance(nonce, str) or not nonce:
        return False
    digest = hashlib.sha256(f"{challenge}:{nonce}".encode("utf-8")).digest()
    return _leading_zero_bits(digest) >= difficulty_bits


import threading

SUBMISSIONS_PER_CYCLE = 3

_QUOTA: dict[tuple[str, str], int] = {}
_QUOTA_LOCK = threading.Lock()


def reset_quota_for_tests() -> None:
    with _QUOTA_LOCK:
        _QUOTA.clear()


def check_and_consume_quota(submitter_hash_value: str, cycle_id: str) -> bool:
    key = (submitter_hash_value, cycle_id)
    with _QUOTA_LOCK:
        used = _QUOTA.get(key, 0)
        if used >= SUBMISSIONS_PER_CYCLE:
            return False
        _QUOTA[key] = used + 1
        return True
