from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections import Counter
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
PUBLIC_DIR = ROOT / "public"
DATA_DIR = ROOT / "data"
WORKER_DIR = ROOT / "worker" / "copilot_handoff"
NOTES_PATH = DATA_DIR / "notes.json"
WORKER_INTERVAL_SECONDS = 15 * 60

STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "by",
    "for",
    "from",
    "how",
    "i",
    "in",
    "is",
    "it",
    "of",
    "on",
    "or",
    "our",
    "please",
    "that",
    "the",
    "this",
    "to",
    "we",
    "with",
}

NOTES_LOCK = threading.Lock()


def ensure_storage() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    WORKER_DIR.mkdir(parents=True, exist_ok=True)
    if not NOTES_PATH.exists():
        NOTES_PATH.write_text("[]", encoding="utf-8")


def load_notes() -> list[dict[str, Any]]:
    ensure_storage()
    with NOTES_LOCK:
        raw = NOTES_PATH.read_text(encoding="utf-8")
        return json.loads(raw or "[]")


def save_notes(notes: list[dict[str, Any]]) -> None:
    ensure_storage()
    with NOTES_LOCK:
        NOTES_PATH.write_text(json.dumps(notes, indent=2), encoding="utf-8")


def summarize_notes(notes: list[dict[str, Any]]) -> dict[str, Any]:
    texts = [str(note.get("text", "")).strip() for note in notes if str(note.get("text", "")).strip()]
    if not texts:
        return {
            "summary": "No suggestions were added in this cycle.",
            "top_topics": [],
            "suggestions_count": 0,
        }

    joined = " ".join(texts).lower()
    words = re.findall(r"[a-zA-Z]{3,}", joined)
    topics = [word for word in words if word not in STOPWORDS]
    common_topics = [word for word, _ in Counter(topics).most_common(5)]
    summary = f"Collected {len(texts)} suggestion(s). Top themes: {', '.join(common_topics) if common_topics else 'general improvements'}."
    return {
        "summary": summary,
        "top_topics": common_topics,
        "suggestions_count": len(texts),
    }


def write_handoff(summary_payload: dict[str, Any], notes: list[dict[str, Any]]) -> None:
    ensure_storage()
    timestamp = datetime.now(timezone.utc).isoformat()
    handoff = {
        "generated_at_utc": timestamp,
        "summary": summary_payload["summary"],
        "top_topics": summary_payload["top_topics"],
        "suggestions_count": summary_payload["suggestions_count"],
        "notes": notes,
    }
    (WORKER_DIR / "latest_handoff.json").write_text(
        json.dumps(handoff, indent=2),
        encoding="utf-8",
    )

    suggestions = "\n".join(f"- {str(note.get('text', '')).strip()}" for note in notes if str(note.get("text", "")).strip())
    copilot_prompt = (
        "# Copilot task handoff\n\n"
        f"Generated at: {timestamp}\n\n"
        f"Summary: {summary_payload['summary']}\n\n"
        "Please implement the following user suggestions when relevant:\n"
        f"{suggestions or '- No suggestions this cycle.'}\n"
    )
    (WORKER_DIR / "copilot_task.md").write_text(copilot_prompt, encoding="utf-8")


def run_worker() -> None:
    while True:
        notes = load_notes()
        summary_payload = summarize_notes(notes)
        write_handoff(summary_payload, notes)
        time.sleep(WORKER_INTERVAL_SECONDS)


class MatrixHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, directory=str(PUBLIC_DIR), **kwargs)

    def _send_json(self, payload: Any, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/notes":
            self._send_json(load_notes())
            return
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/api/notes":
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        payload = self._read_json()
        text = str(payload.get("text", "")).strip()
        if not text:
            self._send_json({"error": "text is required"}, status=HTTPStatus.BAD_REQUEST)
            return

        note = {
            "id": str(uuid.uuid4()),
            "text": text[:500],
            "x": int(payload.get("x", 40)),
            "y": int(payload.get("y", 40)),
            "color": str(payload.get("color", "#ffe98f"))[:20],
            "createdAt": datetime.now(timezone.utc).isoformat(),
        }
        notes = load_notes()
        notes.append(note)
        save_notes(notes)
        self._send_json(note, status=HTTPStatus.CREATED)

    def do_PUT(self) -> None:  # noqa: N802
        if not self.path.startswith("/api/notes/"):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        note_id = self.path.split("/api/notes/", 1)[-1]
        payload = self._read_json()
        notes = load_notes()
        for note in notes:
            if note.get("id") == note_id:
                note["x"] = int(payload.get("x", note.get("x", 40)))
                note["y"] = int(payload.get("y", note.get("y", 40)))
                text = payload.get("text")
                if text is not None:
                    text = str(text).strip()
                    if text:
                        note["text"] = text[:500]
                save_notes(notes)
                self._send_json(note)
                return

        self.send_error(HTTPStatus.NOT_FOUND, "Note not found")


def main() -> None:
    ensure_storage()
    worker = threading.Thread(target=run_worker, daemon=True)
    worker.start()

    server = ThreadingHTTPServer(("127.0.0.1", 8000), MatrixHandler)
    print("TheMatrix running at http://127.0.0.1:8000")
    server.serve_forever()


if __name__ == "__main__":
    main()
