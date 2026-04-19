from __future__ import annotations

import json
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
PUBLIC_DIR = ROOT / "public"
GENERATED_DIR = PUBLIC_DIR / "generated"
LAST_GOOD_DIR = GENERATED_DIR / ".last_good"
WORKER_DIR = ROOT / "worker" / "copilot_handoff"
CYCLES_DIR = DATA_DIR / "cycles"

NOTES_PATH = DATA_DIR / "notes.json"
CURRENT_CYCLE_PATH = DATA_DIR / "current_cycle.json"
RUNS_PATH = DATA_DIR / "runs.json"
SALT_PATH = DATA_DIR / "salt.json"

_LOCKS: dict[str, threading.Lock] = {}
_LOCKS_GUARD = threading.Lock()


def _lock_for(path: Path) -> threading.Lock:
    key = str(path.resolve())
    with _LOCKS_GUARD:
        lock = _LOCKS.get(key)
        if lock is None:
            lock = threading.Lock()
            _LOCKS[key] = lock
        return lock


@contextmanager
def with_lock(path: Path):
    lock = _lock_for(path)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    raw = path.read_text(encoding="utf-8")
    if not raw:
        return default
    return json.loads(raw)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def ensure_dirs() -> None:
    for directory in (DATA_DIR, CYCLES_DIR, WORKER_DIR, GENERATED_DIR, LAST_GOOD_DIR):
        directory.mkdir(parents=True, exist_ok=True)
