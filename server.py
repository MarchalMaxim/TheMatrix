from __future__ import annotations

import hashlib   # KEEP — required by author_label_from_ip
import json
import os
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

import storage
import abuse
import logs
import lint
import agent as agent_mod

PUBLIC_DIR = storage.PUBLIC_DIR
DATA_DIR = storage.DATA_DIR
WORKER_DIR = storage.WORKER_DIR
NOTES_PATH = storage.NOTES_PATH
WORKER_INTERVAL_SECONDS = 4 * 60 * 60  # 4h between cycles

STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from",
    "how", "i", "in", "is", "it", "of", "on", "or", "our", "please",
    "that", "the", "this", "to", "we", "with",
}

PUBLIC_RUN_FIELDS = ("run_id", "cycle_id", "status", "created_at", "started_at", "finished_at", "pr_url")

NOTES_LOCK = threading.Lock()
WORKER_STATE_LOCK = threading.Lock()
# Set this event to wake the worker early (debug / manual trigger)
_TRIGGER_EVENT = threading.Event()
WORKER_STATE: dict[str, Any] = {
    "summary": "Waiting for the first summary cycle...",
    "top_topics": [],
    "suggestions_count": 0,
    "last_run_utc": None,
    "next_run_epoch": None,
    "cycle_id": None,
}

AGENT = agent_mod.make_agent()


# === UX hotfix: preserved ===
ANIMAL_ADJ = [
    "misty", "brave", "lazy", "quick", "wise", "bold", "calm", "loud",
    "tiny", "wild", "swift", "merry", "sleepy", "snappy", "fuzzy", "feral",
]
ANIMAL_NOUN = [
    "fox", "otter", "cat", "owl", "wolf", "bee", "frog", "crow",
    "lynx", "mole", "bat", "hare", "stag", "newt", "wren", "lark",
]


def author_label_from_ip(ip: str) -> str:
    digest = hashlib.sha256(ip.encode("utf-8")).digest()
    adj = ANIMAL_ADJ[digest[0] % len(ANIMAL_ADJ)]
    noun = ANIMAL_NOUN[digest[1] % len(ANIMAL_NOUN)]
    return f"{adj} {noun}"


def ensure_storage() -> None:
    storage.ensure_dirs()
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
    (storage.WORKER_DIR / "latest_handoff.json").write_text(
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
    (storage.WORKER_DIR / "copilot_task.md").write_text(copilot_prompt, encoding="utf-8")


def update_worker_state(summary_payload: dict[str, Any], timestamp: datetime, next_run_epoch: float) -> None:
    with WORKER_STATE_LOCK:
        WORKER_STATE["summary"] = summary_payload["summary"]
        WORKER_STATE["top_topics"] = summary_payload["top_topics"]
        WORKER_STATE["suggestions_count"] = summary_payload["suggestions_count"]
        WORKER_STATE["last_run_utc"] = timestamp.isoformat()
        WORKER_STATE["next_run_epoch"] = next_run_epoch


def get_worker_status() -> dict[str, Any]:
    with WORKER_STATE_LOCK:
        next_run_epoch = WORKER_STATE.get("next_run_epoch")
        seconds_until_next_cycle = 0
        if isinstance(next_run_epoch, (int, float)):
            seconds_until_next_cycle = max(0, int(next_run_epoch - time.time()))
        return {
            "summary": WORKER_STATE["summary"],
            "top_topics": WORKER_STATE["top_topics"],
            "suggestions_count": WORKER_STATE["suggestions_count"],
            "last_run_utc": WORKER_STATE["last_run_utc"],
            "next_run_epoch": next_run_epoch,
            "seconds_until_next_cycle": seconds_until_next_cycle,
            "interval_seconds": WORKER_INTERVAL_SECONDS,
            "cycle_id": WORKER_STATE.get("cycle_id"),
        }


TOP_K = 10


def open_cycle() -> dict[str, Any]:
    cycle_id = f"cycle-{uuid.uuid4().hex[:8]}"
    started_at = datetime.now(timezone.utc).isoformat()
    record = {
        "cycle_id": cycle_id,
        "started_at": started_at,
        "ends_at": None,
    }
    storage.write_json(storage.CURRENT_CYCLE_PATH, record)
    with WORKER_STATE_LOCK:
        WORKER_STATE["cycle_id"] = cycle_id
    logs.log("info", "cycle opened", cycle_id=cycle_id)
    return record


def close_cycle() -> str:
    notes = load_notes()
    cycle = storage.read_json(storage.CURRENT_CYCLE_PATH, default=None)
    if cycle is None:
        cycle = open_cycle()
    cycle_id = cycle["cycle_id"]

    sorted_notes = sorted(
        notes,
        key=lambda n: (-int(n.get("votes", 0)), n.get("createdAt", "")),
    )
    top_notes = sorted_notes[:TOP_K]
    summary_payload = summarize_notes(top_notes)
    write_handoff(summary_payload, top_notes)

    handoff: agent_mod.Handoff = {
        "summary": summary_payload["summary"],
        "top_topics": summary_payload["top_topics"],
        "notes": top_notes,
    }
    ended_at = datetime.now(timezone.utc).isoformat()

    initial_status = "queued"
    initial_error = None
    try:
        run_id = AGENT.kick_off(handoff)
    except agent_mod.AgentError as exc:
        run_id = f"failed-{uuid.uuid4().hex[:8]}"
        initial_status = "failed"
        initial_error = str(exc)
        logs.log("error", "agent kick_off failed", cycle_id=cycle_id, error=str(exc))

    archive = {
        "cycle_id": cycle_id,
        "started_at": cycle.get("started_at"),
        "ended_at": ended_at,
        "top_notes": top_notes,
        "summary": summary_payload["summary"],
        "run_id": run_id,
    }
    storage.write_json(storage.CYCLES_DIR / f"{cycle_id}.json", archive)

    runs = storage.read_json(storage.RUNS_PATH, default=[])
    runs.append({
        "run_id": run_id,
        "cycle_id": cycle_id,
        "status": initial_status,
        "created_at": ended_at,
        "started_at": None,
        "finished_at": ended_at if initial_status == "failed" else None,
        "agent_run_url": None,
        "pr_url": None,
        "artifact_path": None,
        "error": initial_error,
    })
    storage.write_json(storage.RUNS_PATH, runs)

    save_notes([])
    open_cycle()

    update_worker_state(summary_payload, datetime.now(timezone.utc), time.time() + WORKER_INTERVAL_SECONDS)
    logs.log("info", "cycle closed", cycle_id=cycle_id, run_id=run_id, kept=len(top_notes))
    return run_id


def run_worker() -> None:
    existing = storage.read_json(storage.CURRENT_CYCLE_PATH, default=None)
    if existing is None:
        cycle = open_cycle()
        started_ts = time.time()
    else:
        cycle = existing
        with WORKER_STATE_LOCK:
            WORKER_STATE["cycle_id"] = existing.get("cycle_id")
        try:
            started_ts = datetime.fromisoformat(existing["started_at"]).timestamp()
        except (KeyError, ValueError):
            started_ts = time.time()

    # Initialise the countdown so the frontend shows a real value immediately.
    next_run = started_ts + WORKER_INTERVAL_SECONDS
    with WORKER_STATE_LOCK:
        WORKER_STATE["next_run_epoch"] = next_run

    while True:
        # Sleep until next scheduled run OR until manually triggered.
        wait_secs = max(0.0, next_run - time.time())
        _TRIGGER_EVENT.wait(timeout=wait_secs)
        _TRIGGER_EVENT.clear()
        try:
            close_cycle()  # updates WORKER_STATE["next_run_epoch"] internally
        except Exception as exc:
            logs.log("error", f"close_cycle failed: {exc}")
        with WORKER_STATE_LOCK:
            next_run = WORKER_STATE.get("next_run_epoch") or (time.time() + WORKER_INTERVAL_SECONDS)


RUN_POLLER_INTERVAL_SECONDS = 10
MAX_RUN_DURATION_SECONDS = 60 * 60  # 1 hour: stuck runs marked failed
TERMINAL_STATUSES = {"applied", "rejected", "failed"}


def _parse_iso(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def _populate_urls(run: dict[str, Any], status: agent_mod.RunStatus) -> bool:
    """Copy agent_run_url / pr_url from status into run if newly known. Returns True if changed."""
    changed = False
    if status.agent_run_url and run.get("agent_run_url") != status.agent_run_url:
        run["agent_run_url"] = status.agent_run_url
        changed = True
    if status.pr_url and run.get("pr_url") != status.pr_url:
        run["pr_url"] = status.pr_url
        changed = True
    return changed


def _apply_for_run(run: dict[str, Any]) -> None:
    """Fetch artifact, lint+apply, write outcome onto run dict in place."""
    try:
        artifact = AGENT.fetch_artifact(run["run_id"])
    except agent_mod.AgentError as exc:
        run["status"] = "failed"
        run["error"] = f"fetch_artifact: {exc}"
        logs.log("error", "fetch_artifact failed", run_id=run["run_id"], error=str(exc))
        return
    try:
        result = lint.apply_artifact(artifact)
    except Exception as exc:
        run["status"] = "failed"
        run["error"] = f"apply errored: {exc}"
        logs.log("error", "apply errored", run_id=run["run_id"], error=str(exc))
        return
    if result.applied:
        run["status"] = "applied"
        run["artifact_path"] = str(storage.GENERATED_DIR / "theme.css")
        logs.log("info", "artifact applied", run_id=run["run_id"])
    else:
        run["status"] = "rejected"
        run["error"] = result.reason
        lint.restore_last_good()
        logs.log("warn", "artifact rejected; reverted", run_id=run["run_id"], reason=result.reason)


def poll_runs_once() -> None:
    """Single sweep of all non-terminal runs.

    `applying` is treated as recoverable: if the server crashed mid-apply,
    the next poll re-fetches and re-applies (idempotent — same artifact, same result).
    """
    runs = storage.read_json(storage.RUNS_PATH, default=[])
    if not runs:
        return
    changed = False
    now = time.time()
    for run in runs:
        if run["status"] in TERMINAL_STATUSES:
            continue

        # stuck-run timeout
        created = _parse_iso(run.get("created_at"))
        if created is not None and now - created > MAX_RUN_DURATION_SECONDS:
            run["status"] = "failed"
            run["error"] = f"stuck for >{MAX_RUN_DURATION_SECONDS}s"
            run["finished_at"] = datetime.now(timezone.utc).isoformat()
            logs.log("error", "run timed out", run_id=run["run_id"])
            changed = True
            continue

        # poll the adapter
        try:
            status = AGENT.poll(run["run_id"])
        except agent_mod.AgentError as exc:
            run["status"] = "failed"
            run["error"] = str(exc)
            run["finished_at"] = datetime.now(timezone.utc).isoformat()
            logs.log("error", "poll failed", run_id=run["run_id"], error=str(exc))
            changed = True
            continue

        if _populate_urls(run, status):
            changed = True

        # `applying` means we crashed mid-apply previously; re-run apply now
        if run["status"] == "applying":
            _apply_for_run(run)
            run["finished_at"] = datetime.now(timezone.utc).isoformat()
            changed = True
            continue

        if status.status == "queued":
            continue
        if status.status == "failed":
            run["status"] = "failed"
            run["error"] = status.error or "agent reported failed"
            run["finished_at"] = datetime.now(timezone.utc).isoformat()
            changed = True
            continue
        if status.status == "running" and run["status"] != "running":
            run["status"] = "running"
            run["started_at"] = datetime.now(timezone.utc).isoformat()
            changed = True
            continue
        if status.status == "needs_merge" and run["status"] != "needs_merge":
            run["status"] = "needs_merge"
            changed = True
            continue
        if status.status == "merged":
            run["status"] = "applying"
            _apply_for_run(run)
            run["finished_at"] = datetime.now(timezone.utc).isoformat()
            changed = True
            continue
    if changed:
        storage.write_json(storage.RUNS_PATH, runs)


# ------------------------------------------------------------------
# Commit history (/api/history) — fetched from GitHub, cached briefly
# ------------------------------------------------------------------
_HISTORY_CACHE: dict[str, Any] = {"ts": 0.0, "data": []}
_HISTORY_CACHE_TTL_SECONDS = 60
_HISTORY_LOCK = threading.Lock()
_HISTORY_MAX = 30


def _fetch_commit_history() -> list[dict[str, Any]]:
    """Return recent cycle commits, cached for _HISTORY_CACHE_TTL_SECONDS.

    Non-fatal on any error — returns cached data (possibly stale, possibly
    empty) rather than breaking the frontend. Only shows commits whose
    message starts with 'cycle-'.
    """
    with _HISTORY_LOCK:
        if time.time() - _HISTORY_CACHE["ts"] < _HISTORY_CACHE_TTL_SECONDS:
            return _HISTORY_CACHE["data"]

    owner = os.environ.get("GITHUB_OWNER")
    repo = os.environ.get("GITHUB_REPO")
    token = os.environ.get("GITHUB_TOKEN")
    if not (owner and repo):
        return []

    url = f"https://api.github.com/repos/{owner}/{repo}/commits?per_page={_HISTORY_MAX}"
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "TheMatrix-server/1.0",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    import urllib.request as _req
    import urllib.error as _err
    try:
        request = _req.Request(url, headers=headers, method="GET")
        with _req.urlopen(request, timeout=10) as resp:
            raw = resp.read()
        commits = json.loads(raw.decode("utf-8"))
    except (_err.URLError, _err.HTTPError, json.JSONDecodeError, OSError) as exc:
        logs.log("warn", "history fetch failed", error=str(exc))
        with _HISTORY_LOCK:
            return _HISTORY_CACHE["data"]  # stale or empty

    trimmed: list[dict[str, Any]] = []
    for c in commits:
        message = ((c.get("commit") or {}).get("message") or "")
        title = message.split("\n", 1)[0]
        if not title.startswith("cycle-"):
            continue
        author = ((c.get("commit") or {}).get("author") or {})
        trimmed.append({
            "sha": c.get("sha", "")[:12],
            "title": title,
            "date": author.get("date"),
            "html_url": c.get("html_url"),
        })

    with _HISTORY_LOCK:
        _HISTORY_CACHE["ts"] = time.time()
        _HISTORY_CACHE["data"] = trimmed
    return trimmed


def run_poller() -> None:
    while True:
        try:
            poll_runs_once()
        except Exception as exc:
            logs.log("error", f"poller errored: {exc}")
        time.sleep(RUN_POLLER_INTERVAL_SECONDS)


class NoteBoardHandler(SimpleHTTPRequestHandler):
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

    # ------------------------------------------------------------------
    # Helpers shared across handlers
    # ------------------------------------------------------------------

    def _sanitize_note(self, note: dict[str, Any], caller_hash: str) -> dict[str, Any]:
        """Return a public-safe copy of a note: drop internal fields, add is_owner."""
        out = {k: v for k, v in note.items() if k not in ("voter_hashes", "submitter_hash")}
        out["is_owner"] = note.get("submitter_hash") == caller_hash
        return out

    # ------------------------------------------------------------------
    # /logs helpers
    # ------------------------------------------------------------------

    def _logs_token(self) -> str | None:
        return os.environ.get("LOGS_TOKEN") or None

    def _query_param(self, name: str) -> str | None:
        if "?" not in self.path:
            return None
        qs = self.path.split("?", 1)[1]
        for part in qs.split("&"):
            if "=" in part:
                k, v = part.split("=", 1)
                if k == name:
                    return v
        return None

    def _render_logs_page(self) -> str:
        import html as html_mod
        runs = storage.read_json(storage.RUNS_PATH, default=[])
        log_entries = logs.recent()

        rows = []
        for r in reversed(runs[-50:]):
            merge_btn = ""
            if r.get("status") == "needs_merge":
                run_id_esc = html_mod.escape(r.get("run_id", ""))
                merge_btn = (
                    f'<form method="post" action="/logs/merge" style="display:inline">'
                    f'<input type="hidden" name="run_id" value="{run_id_esc}">'
                    f'<input type="hidden" name="token" value="{html_mod.escape(self._logs_token() or "")}">'
                    f'<button type="submit">Merge</button>'
                    f'</form>'
                )
            status = html_mod.escape(str(r.get("status", "")))
            run_id = html_mod.escape(str(r.get("run_id", "")))
            cycle_id = html_mod.escape(str(r.get("cycle_id", "")))
            error = html_mod.escape(str(r.get("error") or ""))
            rows.append(
                f"<tr><td>{run_id}</td><td>{cycle_id}</td><td>{status}</td>"
                f"<td style='max-width:600px;color:#a00;white-space:pre-wrap'>{error}</td>"
                f"<td>{merge_btn}</td></tr>"
            )

        # Render full log entries including all structured extras (error,
        # cycle_id, run_id, etc.) — these are critical for debugging.
        STD_FIELDS = {"ts", "level", "message"}
        LEVEL_COLORS = {"error": "#a00", "warn": "#a60", "info": "#357", "debug": "#666"}
        log_lines = []
        for entry in reversed(log_entries[-200:]):
            level = entry.get("level", "")
            color = LEVEL_COLORS.get(level, "#333")
            level_esc = html_mod.escape(level)
            msg = html_mod.escape(entry.get("message", ""))
            ts = html_mod.escape(entry.get("ts", ""))
            extras = " ".join(
                f"<i>{html_mod.escape(k)}=</i>{html_mod.escape(str(v))}"
                for k, v in entry.items() if k not in STD_FIELDS
            )
            log_lines.append(
                f"<li>[{ts}] <b style='color:{color}'>{level_esc}</b> "
                f"{msg} <span style='color:#666'>{extras}</span></li>"
            )

        token_esc = html_mod.escape(self._logs_token() or "")
        return (
            "<!doctype html><html><head><meta charset=utf-8>"
            "<title>TheMatrix — Operator Logs</title>"
            "<style>body{font-family:monospace;padding:1rem}"
            "table{border-collapse:collapse;width:100%}"
            "td,th{border:1px solid #ccc;padding:0.4rem 0.6rem;text-align:left}"
            "ul{list-style:none;padding:0}li{margin:0.2rem 0}"
            "button{cursor:pointer}"
            "</style></head><body>"
            "<h1>Operator Logs</h1>"
            "<p>"
            "<button onclick=\""
            f"fetch('/api/trigger-cycle',{{method:'POST',headers:{{'Content-Type':'application/json'}},"
            f"body:JSON.stringify({{token:'{token_esc}'}})}})"
            ".then(r=>r.ok?location.reload():alert('trigger failed: '+r.status))"
            "\">"
            "⚡ Trigger cycle now"
            "</button>"
            "</p>"
            "<h2>Run Queue</h2>"
            f"<table><tr><th>run_id</th><th>cycle_id</th><th>status</th><th>error</th><th>action</th></tr>"
            f"{''.join(rows)}</table>"
            "<h2>Recent Log</h2>"
            f"<ul>{''.join(log_lines)}</ul>"
            "</body></html>"
        )

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/notes":
            caller_hash = self._submitter_hash()
            all_notes = load_notes()
            self._send_json([self._sanitize_note(n, caller_hash) for n in all_notes])
            return
        if self.path == "/api/worker-status":
            self._send_json(get_worker_status()); return
        if self.path == "/api/pow-challenge":
            voter = self._submitter_hash()
            cycle_id = self._current_cycle_id()
            challenge = abuse.make_pow_challenge(cycle_id, voter)
            self._send_json({
                "challenge": challenge,
                "difficulty_submit": abuse.POW_DIFFICULTY_SUBMIT,
                "difficulty_vote": abuse.POW_DIFFICULTY_VOTE,
            })
            return
        if self.path == "/api/history" or self.path.startswith("/api/history?"):
            self._send_json(_fetch_commit_history())
            return
        if self.path == "/api/runs":
            runs = storage.read_json(storage.RUNS_PATH, default=[])
            sanitised = [{k: r.get(k) for k in PUBLIC_RUN_FIELDS} for r in runs[-10:]]
            self._send_json(sanitised); return
        if self.path == "/api/cycle/current":
            self._send_json(storage.read_json(storage.CURRENT_CYCLE_PATH, default={})); return
        cycle_match = re.match(r"^/api/cycle/([^/]+)$", self.path)
        if cycle_match:
            cycle_id = cycle_match.group(1)
            archive = storage.read_json(storage.CYCLES_DIR / f"{cycle_id}.json", default=None)
            if archive is None:
                self.send_error(HTTPStatus.NOT_FOUND, "Not Found"); return
            self._send_json(archive); return
        # /logs — token-gated operator page
        logs_path = self.path.split("?", 1)[0]
        if logs_path == "/logs":
            expected = self._logs_token()
            provided = self._query_param("token")
            if not expected or provided != expected:
                self.send_error(HTTPStatus.NOT_FOUND, "Not Found"); return
            body = self._render_logs_page().encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        return super().do_GET()

    def _client_ip(self) -> str:
        return self.client_address[0]

    def _user_agent(self) -> str:
        return self.headers.get("User-Agent", "")

    def _current_cycle_id(self) -> str:
        cycle = storage.read_json(storage.CURRENT_CYCLE_PATH, default={})
        return cycle.get("cycle_id", "cycle-bootstrap")

    def _submitter_hash(self) -> str:
        salt = storage.get_daily_salt(today=datetime.now(timezone.utc).date().isoformat())
        return abuse.submitter_hash(self._client_ip(), self._user_agent(), salt=salt)

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/notes":
            return self._handle_create_note()
        if self.path == "/logs/merge":
            return self._handle_logs_merge()
        if self.path == "/api/trigger-cycle":
            return self._handle_trigger_cycle()
        vote_match = re.match(r"^/api/notes/([^/]+)/vote$", self.path)
        if vote_match:
            return self._handle_vote(vote_match.group(1))
        self.send_error(HTTPStatus.NOT_FOUND, "Not Found")

    def _handle_trigger_cycle(self) -> None:
        """Operator endpoint: wake the worker early to close the current cycle.

        Gated by LOGS_TOKEN — either via JSON body {"token": "..."} or the
        X-Logs-Token header. Returns 404 (not 401/403) on failure so the
        endpoint is indistinguishable from "not found" to scanners.
        """
        expected = self._logs_token()
        # Accept token from body OR header for flexibility
        header_token = self.headers.get("X-Logs-Token", "")
        body_token = ""
        try:
            payload = self._read_json()
            body_token = str(payload.get("token", ""))
        except Exception:  # noqa: BLE001
            pass
        provided = body_token or header_token
        if not expected or provided != expected:
            logs.log("warn", "cycle trigger rejected",
                     ip=self._client_ip(), reason="bad or missing token")
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        _TRIGGER_EVENT.set()
        logs.log("info", "cycle trigger requested", ip=self._client_ip())
        self._send_json({"triggered": True})

    def _handle_logs_merge(self) -> None:
        """Mock-merge action: only works when AGENT.is_mock is True."""
        payload = self._read_json()
        run_id = str(payload.get("run_id", ""))
        token = str(payload.get("token", ""))
        expected = self._logs_token()
        if not expected or token != expected:
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        if not AGENT.is_mock:
            self._send_json({"error": "merge only available for mock agent"}, status=HTTPStatus.BAD_REQUEST)
            return
        try:
            AGENT.signal_merge(run_id)  # type: ignore[attr-defined]
        except agent_mod.AgentError as exc:
            self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return
        logs.log("info", "mock merge signalled", run_id=run_id)
        self._send_json({"merged": True})

    def _handle_create_note(self) -> None:
        payload = self._read_json()
        text = str(payload.get("text", "")).strip()
        nonce = str(payload.get("pow", ""))
        challenge = str(payload.get("challenge", ""))
        voter = self._submitter_hash()
        cycle_id = self._current_cycle_id()
        expected = abuse.make_pow_challenge(cycle_id, voter)
        if challenge != expected:
            logs.log("warn", "create rejected: stale challenge", voter=voter)
            self._send_json({"error": "stale challenge"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not abuse.verify_pow(challenge, nonce, abuse.POW_DIFFICULTY_SUBMIT):
            logs.log("warn", "create rejected: bad pow", voter=voter)
            self._send_json({"error": "invalid proof of work"}, status=HTTPStatus.BAD_REQUEST)
            return
        ok, reason = abuse.lint_submission(text)
        if not ok:
            logs.log("warn", "create rejected: content lint", voter=voter, reason=reason)
            self._send_json({"error": reason}, status=HTTPStatus.BAD_REQUEST)
            return
        if not abuse.check_and_consume_quota(voter, cycle_id):
            logs.log("warn", "create rejected: quota", voter=voter, cycle=cycle_id)
            self._send_json({"error": "submission quota exceeded for this cycle"}, status=429)
            return

        note = {
            "id": str(uuid.uuid4()),
            "text": text[:500],
            "x": int(payload.get("x", 40)),
            "y": int(payload.get("y", 40)),
            "color": str(payload.get("color", "#ffe98f"))[:20],
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "votes": 0,
            "voter_hashes": [],
            "submitter_hash": voter,
            "cycle_id": cycle_id,
            "author_label": author_label_from_ip(self._client_ip()),
        }
        notes = load_notes()
        notes.append(note)
        save_notes(notes)
        logs.log("info", "note created", note_id=note["id"], voter=voter, cycle=cycle_id)
        self._send_json(self._sanitize_note(note, voter), status=HTTPStatus.CREATED)

    def _handle_vote(self, note_id: str) -> None:
        payload = self._read_json()
        nonce = str(payload.get("pow", ""))
        challenge = str(payload.get("challenge", ""))
        voter = self._submitter_hash()
        expected_challenge = abuse.make_pow_challenge(self._current_cycle_id(), voter)
        if challenge != expected_challenge:
            self._send_json({"error": "stale challenge"}, status=HTTPStatus.BAD_REQUEST)
            return
        if not abuse.verify_pow(challenge, nonce, abuse.POW_DIFFICULTY_VOTE):
            self._send_json({"error": "invalid proof of work"}, status=HTTPStatus.BAD_REQUEST)
            return

        notes = load_notes()
        for note in notes:
            if note.get("id") == note_id:
                voters = note.setdefault("voter_hashes", [])
                if voter in voters:
                    voters.remove(voter)
                else:
                    voters.append(voter)
                note["votes"] = len(voters)
                save_notes(notes)
                self._send_json(self._sanitize_note(note, voter))
                return
        self.send_error(HTTPStatus.NOT_FOUND, "Note not found")

    def do_PUT(self) -> None:  # noqa: N802
        if not self.path.startswith("/api/notes/"):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return

        note_id = self.path.split("/api/notes/", 1)[-1]
        payload = self._read_json()
        notes = load_notes()
        caller_hash = self._submitter_hash()
        for note in notes:
            if note.get("id") == note_id:
                # Text edits require ownership; position changes (drag) are open to all.
                text = payload.get("text")
                if text is not None:
                    if note.get("submitter_hash") != caller_hash:
                        self._send_json({"error": "not the owner"}, status=HTTPStatus.FORBIDDEN)
                        return
                    text = str(text).strip()
                    if text:
                        note["text"] = text[:500]
                if "x" in payload:
                    note["x"] = int(payload["x"])
                if "y" in payload:
                    note["y"] = int(payload["y"])
                save_notes(notes)
                self._send_json(self._sanitize_note(note, caller_hash))
                return

        self.send_error(HTTPStatus.NOT_FOUND, "Note not found")

    def do_DELETE(self) -> None:  # noqa: N802
        if not self.path.startswith("/api/notes/"):
            self.send_error(HTTPStatus.NOT_FOUND, "Not Found")
            return
        note_id = self.path.split("/api/notes/", 1)[-1]
        return self._handle_delete_note(note_id)

    def _handle_delete_note(self, note_id: str) -> None:
        caller_hash = self._submitter_hash()
        notes = load_notes()
        for i, note in enumerate(notes):
            if note.get("id") == note_id:
                if note.get("submitter_hash") != caller_hash:
                    self._send_json({"error": "not the owner"}, status=HTTPStatus.FORBIDDEN)
                    return
                notes.pop(i)
                save_notes(notes)
                logs.log("info", "note deleted", note_id=note_id, voter=caller_hash)
                self._send_json({"deleted": True})
                return
        self.send_error(HTTPStatus.NOT_FOUND, "Note not found")


def main() -> None:
    storage.ensure_dirs()
    if not NOTES_PATH.exists():
        NOTES_PATH.write_text("[]", encoding="utf-8")
    threading.Thread(target=run_worker, daemon=True).start()
    threading.Thread(target=run_poller, daemon=True).start()
    # Cloud Run injects PORT; bind 0.0.0.0 so the container is reachable.
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), NoteBoardHandler)
    print(f"TheMatrix running at http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
