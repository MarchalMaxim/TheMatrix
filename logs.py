from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

CAPACITY = 500

_BUFFER: deque[dict[str, Any]] = deque(maxlen=CAPACITY)
_LOCK = threading.Lock()


def log(level: str, message: str, **fields: Any) -> None:
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "message": message,
        **fields,
    }
    with _LOCK:
        _BUFFER.append(record)


def recent() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_BUFFER)


def reset_for_tests() -> None:
    with _LOCK:
        _BUFFER.clear()
