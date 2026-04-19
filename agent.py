"""Agent adapter for kicking off coding-agent runs.

Threading contract: implementations MUST be safe to call from multiple
threads. `kick_off` is invoked from the cycle worker thread; `poll` and
`fetch_artifact` are invoked from the run-queue poller thread; `signal_merge`
(mock-only) is invoked from the HTTP handler thread serving /logs/merge.

Status flow (driven by poller, not by adapter):
    queued -> running -> needs_merge -> merged -> applying -> applied | rejected
                                                |
                                                +-> failed (errors at any stage)

`applying` and `applied`/`rejected`/`failed` are the poller's local view of the
run. The adapter only needs to report `queued | running | needs_merge | merged`
(plus `failed` if it encountered an error).
"""

from __future__ import annotations

import hashlib
import os
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol, TypedDict, runtime_checkable


class Handoff(TypedDict, total=False):
    summary: str
    top_topics: list[str]
    notes: list[dict[str, Any]]


class Artifact(TypedDict):
    theme_css: str
    slots: dict[str, str]


@dataclass
class RunStatus:
    """What an adapter reports about an in-flight run.

    `status` is one of: queued | running | needs_merge | merged | failed.
    `agent_run_url` and `pr_url` are populated when the adapter knows them.
    `error` is set when status == "failed".
    """

    status: str
    detail: str = ""
    agent_run_url: str | None = None
    pr_url: str | None = None
    error: str | None = None


class AgentError(RuntimeError):
    """Typed error raised by adapter methods on failure."""


PALETTE = [
    ("#fff5f7", "#ff7faa", "#34495e"),
    ("#f4fff5", "#5fb37c", "#2f4f3a"),
    ("#fffaf0", "#e08a3c", "#5a3a14"),
    ("#f0f4ff", "#6d83d9", "#1f2a55"),
    ("#fdf5ff", "#a25fb3", "#3c1f4a"),
]

FONTS = ["Comic Sans MS", "Trebuchet MS", "Georgia", "Courier New", "Verdana"]


@runtime_checkable
class AgentAdapter(Protocol):
    is_mock: bool

    def kick_off(self, handoff: Handoff) -> str:
        """Trigger a new agent run; return a stable run_id. Raises AgentError."""

    def poll(self, run_id: str) -> RunStatus:
        """Return current status. Raises AgentError if run_id unknown."""

    def fetch_artifact(self, run_id: str) -> Artifact:
        """Return the produced artifact. Raises AgentError if not yet ready."""


class MockGithubAgent:
    """In-process simulator. Status transitions are time-based; merge is operator-driven via signal_merge()."""

    is_mock = True

    def __init__(self, queued_seconds: float = 5.0, running_seconds: float = 30.0):
        self._queued_seconds = queued_seconds
        self._running_seconds = running_seconds
        self._runs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def kick_off(self, handoff: Handoff) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._runs[run_id] = {
                "created_at": time.time(),
                "merged_at": None,
                "summary": handoff.get("summary", ""),
                "top_topics": list(handoff.get("top_topics", [])),
            }
        return run_id

    def poll(self, run_id: str) -> RunStatus:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise AgentError(f"unknown run_id: {run_id}")
            elapsed = time.time() - run["created_at"]
            merged_at = run["merged_at"]
        run_url = f"https://example.invalid/mock/runs/{run_id}"
        pr_url = f"https://example.invalid/mock/pull/{run_id}"
        if merged_at is not None:
            return RunStatus(status="merged", detail="operator merged",
                             agent_run_url=run_url, pr_url=pr_url)
        if elapsed < self._queued_seconds:
            return RunStatus(status="queued", agent_run_url=run_url)
        if elapsed < self._queued_seconds + self._running_seconds:
            return RunStatus(status="running", agent_run_url=run_url)
        return RunStatus(status="needs_merge", detail="awaiting operator merge",
                         agent_run_url=run_url, pr_url=pr_url)

    def signal_merge(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise AgentError(f"unknown run_id: {run_id}")
            if run["merged_at"] is None:
                run["merged_at"] = time.time()

    def fetch_artifact(self, run_id: str) -> Artifact:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise AgentError(f"unknown run_id: {run_id}")
            if run["merged_at"] is None:
                raise AgentError(f"artifact not ready: run {run_id} not yet merged")
            summary = run["summary"]
            topics = run["top_topics"] or ["something"]
        seed = int(hashlib.sha256(summary.encode("utf-8")).hexdigest(), 16)
        bg, accent, ink = PALETTE[seed % len(PALETTE)]
        font = FONTS[(seed >> 8) % len(FONTS)]
        rotation = (seed % 7) - 3
        theme_css = (
            f"body {{ background: {bg}; color: {ink}; font-family: \"{font}\", sans-serif; }}\n"
            f"h1 {{ color: {accent}; transform: rotate({rotation}deg); }}\n"
            f".note {{ background: {bg}; border-color: {accent}; }}\n"
            f"button {{ background: {accent}; }}\n"
            f"#generation-attraction {{ border-color: {accent}; }}\n"
        )
        slots: dict[str, str] = {
            "intro": f"<p>Today's wall channels: <strong>{topics[0]}</strong>.</p>",
            "aside": f"<blockquote>{summary}</blockquote>",
            "footer-extra": f"<p><em>generation seed: {seed % 100000}</em></p>",
        }
        return Artifact(theme_css=theme_css, slots=slots)


class GithubActionsAgent:
    """v2 skeleton: kicks off a workflow_dispatch on a coding-agent workflow,
    polls workflow_run status + linked PR state, downloads artifact on merge.

    Intentionally NotImplementedError throughout in v1 so the protocol is
    exercised structurally without committing to a real network impl yet.
    Wiring the real calls is its own task.
    """

    is_mock = False

    def kick_off(self, handoff: Handoff) -> str:
        # POST /repos/:owner/:repo/actions/workflows/:id/dispatches
        # then locate the run via /actions/runs?event=workflow_dispatch&created>=<ts>
        raise NotImplementedError("GithubActionsAgent.kick_off — wire in v2")

    def poll(self, run_id: str) -> RunStatus:
        # GET /actions/runs/:id -> map status; if completed, look up linked PR
        # PR.merged == True -> RunStatus("merged", pr_url=..., agent_run_url=...)
        # PR open and CI green -> RunStatus("needs_merge", ...)
        raise NotImplementedError("GithubActionsAgent.poll — wire in v2")

    def fetch_artifact(self, run_id: str) -> Artifact:
        # Download the workflow artifact zip; load theme.css + slots.json
        raise NotImplementedError("GithubActionsAgent.fetch_artifact — wire in v2")


def make_agent() -> AgentAdapter:
    """Factory selected by AGENT_KIND env var. Default: mock.
    Treats empty/whitespace AGENT_KIND as missing -> uses default."""
    raw = os.environ.get("AGENT_KIND") or ""
    kind = raw.strip().lower() or "mock"
    if kind == "mock":
        return MockGithubAgent()
    if kind == "github":
        return GithubActionsAgent()
    raise AgentError(f"unknown AGENT_KIND: {raw!r} (expected 'mock' or 'github')")
