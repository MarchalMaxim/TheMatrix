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
import json
import os
import threading
import time
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field
from io import BytesIO
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


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Disables urllib's automatic redirect following by re-raising the
    redirect status as an HTTPError. Critical for the GitHub artifact zip
    endpoint, which redirects to Azure Blob Storage with a pre-signed URL
    that mustn't receive the GitHub Authorization header."""

    def http_error_301(self, req, fp, code, msg, headers):
        raise urllib.error.HTTPError(req.full_url, code, msg, headers, fp)

    http_error_302 = http_error_301
    http_error_303 = http_error_301
    http_error_307 = http_error_301
    http_error_308 = http_error_301


class GithubActionsAgent:
    """Live adapter that dispatches a GitHub Actions workflow and downloads
    the artifact it produces.

    Flow:
      1. kick_off() generates a unique handoff_id and POSTs a workflow_dispatch
         with the handoff payload as inputs. Returns the handoff_id as run_id.
      2. The workflow's `run-name: matrix-handoff-${{ inputs.handoff_id }}` makes
         each run findable. poll() lists recent workflow runs and matches by name.
      3. When the workflow completes successfully we treat that as `merged`
         (the workflow's success is the approval gate — no separate PR step).
      4. fetch_artifact() downloads the artifact zip, extracts theme.css and
         slots.json, and returns them as an Artifact.

    Required env vars:
      GITHUB_TOKEN        — PAT or fine-grained token (actions:write, contents:read)
      GITHUB_OWNER        — repo owner / org
      GITHUB_REPO         — repo name
      GITHUB_WORKFLOW_FILE — workflow filename (default: matrix-handoff.yml)
      GITHUB_REF          — branch/tag to dispatch on (default: main)
    """

    is_mock = False
    _API = "https://api.github.com"

    def __init__(self, *, http_open: Any | None = None) -> None:
        # http_open is injected for tests; defaults to urllib.request.urlopen
        self._http_open = http_open or urllib.request.urlopen
        self.token = os.environ.get("GITHUB_TOKEN") or ""
        self.owner = os.environ.get("GITHUB_OWNER") or ""
        self.repo = os.environ.get("GITHUB_REPO") or ""
        self.workflow = os.environ.get("GITHUB_WORKFLOW_FILE") or "matrix-handoff.yml"
        self.ref = os.environ.get("GITHUB_REF") or "main"
        if not (self.token and self.owner and self.repo):
            raise AgentError(
                "GithubActionsAgent requires GITHUB_TOKEN, GITHUB_OWNER, GITHUB_REPO env vars"
            )

    # ------------------------------------------------------------------
    # HTTP plumbing
    # ------------------------------------------------------------------

    def _request(self, method: str, path: str, body: dict | None = None,
                 *, accept: str = "application/vnd.github+json") -> tuple[int, bytes]:
        url = path if path.startswith("http") else f"{self._API}{path}"
        data = json.dumps(body).encode("utf-8") if body is not None else None
        headers = {
            "Accept": accept,
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "TheMatrix-agent/1.0",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._http_open(req, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "ignore")[:300]
            except Exception:  # noqa: BLE001
                pass
            raise AgentError(f"GitHub API {method} {path}: HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise AgentError(f"GitHub API network error on {method} {path}: {exc}") from exc

    def _api_json(self, method: str, path: str, body: dict | None = None) -> dict:
        status, raw = self._request(method, path, body)
        if not raw:
            return {}
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise AgentError(f"GitHub API returned non-JSON for {path}: {exc}") from exc

    # ------------------------------------------------------------------
    # Adapter API
    # ------------------------------------------------------------------

    def kick_off(self, handoff: Handoff) -> str:
        handoff_id = uuid.uuid4().hex[:12]
        notes_json = json.dumps(handoff.get("notes", []))
        # GitHub workflow_dispatch inputs are limited to ~65KB total. Trim
        # aggressively — the workflow only needs enough context to prompt the
        # generator.
        body = {
            "ref": self.ref,
            "inputs": {
                "handoff_id": handoff_id,
                "summary": (handoff.get("summary", "") or "")[:1000],
                "notes_json": notes_json[:60000],
            },
        }
        # Dispatch returns 204 No Content with no body
        self._request(
            "POST",
            f"/repos/{self.owner}/{self.repo}/actions/workflows/{self.workflow}/dispatches",
            body,
        )
        return handoff_id

    def _find_run(self, handoff_id: str) -> dict | None:
        """Look through the most recent runs of our workflow for one whose
        run-name embeds our handoff_id."""
        data = self._api_json(
            "GET",
            f"/repos/{self.owner}/{self.repo}/actions/workflows/{self.workflow}/runs?per_page=30",
        )
        marker = f"matrix-handoff-{handoff_id}"
        for run in data.get("workflow_runs", []):
            name = (run.get("name") or "") + " " + (run.get("display_title") or "")
            if marker in name or handoff_id in name:
                return run
        return None

    def poll(self, run_id: str) -> RunStatus:
        run = self._find_run(run_id)
        if run is None:
            # Dispatch may take a few seconds before the run appears
            return RunStatus(status="queued", detail="awaiting workflow scheduling")
        run_url = run.get("html_url")
        gh_status = run.get("status")          # queued | in_progress | completed
        gh_conclusion = run.get("conclusion")  # success | failure | cancelled | ...
        if gh_status == "queued":
            return RunStatus(status="queued", agent_run_url=run_url)
        if gh_status == "in_progress":
            return RunStatus(status="running", agent_run_url=run_url)
        if gh_status == "completed":
            if gh_conclusion == "success":
                # Workflow success IS the merge gate for this adapter
                return RunStatus(status="merged", detail="workflow succeeded",
                                 agent_run_url=run_url)
            return RunStatus(status="failed", agent_run_url=run_url,
                             error=f"workflow {gh_conclusion or 'failed'}")
        # Unknown status — treat as still running
        return RunStatus(status="running", agent_run_url=run_url,
                         detail=f"unknown gh status {gh_status!r}")

    def fetch_artifact(self, run_id: str) -> Artifact:
        run = self._find_run(run_id)
        if run is None:
            raise AgentError(f"no GitHub run found for handoff {run_id}")
        if run.get("status") != "completed" or run.get("conclusion") != "success":
            raise AgentError(
                f"workflow not yet successful (status={run.get('status')}, "
                f"conclusion={run.get('conclusion')})"
            )
        gh_run_id = run["id"]
        artifacts = self._api_json(
            "GET",
            f"/repos/{self.owner}/{self.repo}/actions/runs/{gh_run_id}/artifacts",
        )
        items = artifacts.get("artifacts", [])
        if not items:
            raise AgentError(f"no artifacts on run {gh_run_id}")
        # Pick the artifact whose name matches our naming scheme; fall back to first
        chosen = next(
            (a for a in items if run_id in (a.get("name") or "")),
            items[0],
        )
        zip_bytes = self._download_artifact_zip(chosen["id"])
        return self._parse_artifact_zip(zip_bytes)

    def _download_artifact_zip(self, artifact_id: int) -> bytes:
        """Download an artifact zip.

        GitHub's /actions/artifacts/{id}/zip endpoint replies with a 302 to
        Azure Blob Storage. The pre-signed Azure URL must NOT receive the
        GitHub Authorization header (Azure 401s if you send one). urllib's
        default opener auto-follows redirects with all headers, so we
        intercept the 302 ourselves and re-request the Location with a
        minimal header set.
        """
        url = (
            f"{self._API}/repos/{self.owner}/{self.repo}"
            f"/actions/artifacts/{artifact_id}/zip"
        )
        # Step 1 — GitHub side, capture the redirect manually.
        gh_req = urllib.request.Request(
            url,
            method="GET",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "User-Agent": "TheMatrix-agent/1.0",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        opener = urllib.request.build_opener(_NoRedirectHandler())
        try:
            with opener.open(gh_req, timeout=30) as resp:
                # Some endpoints may return 200 directly (older API versions);
                # in that case the body IS the zip.
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code not in (301, 302, 303, 307, 308):
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", "ignore")[:300]
                except Exception:  # noqa: BLE001
                    pass
                raise AgentError(
                    f"GitHub artifact download HTTP {exc.code}: {detail}"
                ) from exc
            location = exc.headers.get("Location")
            if not location:
                raise AgentError("artifact 3xx response without Location header") from exc

        # Step 2 — Azure side, no GitHub auth header.
        blob_req = urllib.request.Request(
            location,
            method="GET",
            headers={"User-Agent": "TheMatrix-agent/1.0"},
        )
        try:
            with self._http_open(blob_req, timeout=60) as r:
                return r.read()
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "ignore")[:300]
            except Exception:  # noqa: BLE001
                pass
            raise AgentError(
                f"artifact blob fetch HTTP {exc.code}: {detail}"
            ) from exc
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise AgentError(f"artifact blob network error: {exc}") from exc

    @staticmethod
    def _parse_artifact_zip(zip_bytes: bytes) -> Artifact:
        css = ""
        slots: dict[str, str] = {}
        try:
            with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
                for name in zf.namelist():
                    base = name.rsplit("/", 1)[-1]
                    if base == "theme.css":
                        css = zf.read(name).decode("utf-8")
                    elif base == "slots.json":
                        slots = json.loads(zf.read(name).decode("utf-8"))
        except (zipfile.BadZipFile, json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise AgentError(f"could not parse artifact zip: {exc}") from exc
        if not css and not slots:
            raise AgentError("artifact zip contained neither theme.css nor slots.json")
        return Artifact(theme_css=css, slots=slots)


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
