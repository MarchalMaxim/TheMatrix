# TheMatrix — Living Wall (v1 Design)

Date: 2026-04-19
Status: Draft, awaiting user review

## 1. Overview

TheMatrix becomes an "r/place for prompts." Users post prompts as post-its on a shared wall. Anyone can upvote any post-it. Every N minutes a worker collects the top-voted post-its, summarizes them, and asks a coding agent (running as a GitHub job, mocked in v1) to produce a new visual theme + small content fragments. The result lands as a pull request in the repo. After a human merges the PR (and eventually the live site redeploys), the site visibly changes for the next cycle. The wall archives, a fresh cycle starts.

The site rewrites itself based on what its visitors collectively suggest.

## 2. Goals & non-goals

**Goals (v1):**
- Submission feed of prompts as post-its with upvotes.
- Cycle timer + summary + handoff to a (mocked) coding agent via a GitHub `workflow_dispatch`-style adapter.
- Queue of agent runs visible to all users on the public site.
- Secret `/logs` endpoint with detailed diagnostics for the operator.
- Three-layer kernel architecture so the agent can change *style* and *free-zone content* but cannot remove core UI or run JS.
- Lint + auto-revert safety net on agent output.
- Anti-abuse: per-cycle submission quota gated by submitter hash + proof-of-work.

**Non-goals (v1, deferred):**
- Real deployment. Will eventually live on a Hetzner VPS; out of scope here.
- Real GitHub API integration. The agent kickoff is mocked behind a small adapter interface; the mock fakes a queued→running→success transition and produces a plausible canned artifact so the full pipeline (lint, apply, render) is exercised end-to-end.
- Real accounts / OAuth / persistent identity.
- Sandboxed-iframe free zone (option C from brainstorming). Architecture leaves the seam.
- Auto-merging PRs. Manual merge by the operator for v1.
- Moderation queue / human content review (basic content lint only).

## 3. Architecture

Three layers in the rendered page:

1. **Hard kernel** — server-rendered, never touched by the agent:
   - Post-it submission widget (fixed bottom-right overlay).
   - Countdown to next cycle + one-line "what is this site" explainer.
   - Public run-queue status badge ("current run: queued / running / merged / failed", last-3 mini-history).
   - "Reset to default look" toggle that ignores generated artifacts client-side.
   - All API routes.
2. **Soft kernel** — HTML structure locked, only restyled via the agent's `theme.css`:
   - `<header>`, `<main id="canvas">`, `<footer>`. Agent can recolor, restyle, animate, but the elements cannot be removed.
3. **Free zone** — fully replaced each cycle from named slots:
   - `<div data-slot="intro">`, `data-slot="aside">`, `data-slot="footer-extra">`. Agent fills with HTML fragments from an allowlisted tag set. No JS, no external resources.

Backend components:

- **HTTP server (`server.py`)** — extends the existing stdlib server with new routes (see §5). Single process, threaded.
- **Cycle worker** — existing thread; replaces in-process summarization with: summarize → write handoff → invoke agent adapter → record queue entry → done. Does not block waiting for the agent.
- **Run-queue poller** — separate thread, ticks every ~10s, asks the agent adapter for status updates on in-flight runs, updates queue records, and (when a run is "merged") triggers the lint+apply step against the run's artifact.
- **Agent adapter** — `agent.py` module with `kick_off(handoff) -> run_id` and `poll(run_id) -> RunStatus`. v1 implementation is `MockGithubAgent`; the real `GithubActionsAgent` is a v2 swap.
- **Lint + apply** — pure function `(artifact) -> ApprovedArtifact | RejectionReason`. Writes accepted artifacts to `public/generated/theme.css` and `public/generated/slots.json`. Keeps `public/generated/.last_good/` as a fallback.
- **Log buffer** — in-memory ring buffer of the last ~500 events (worker errors, lint rejections, abuse blocks, agent transitions). Surfaced via the secret `/logs` endpoint.

## 4. Data model

All file-based JSON under `data/`. No DB.

- `data/notes.json` — list of notes. Each note: `{id, text, x, y, color, createdAt, votes: int, voter_hashes: [str], submitter_hash: str, cycle_id: str}`.
(Vote records are stored inline on the note via `voter_hashes`; no separate votes file.)
- `data/cycles/<cycle_id>.json` — archived cycle: `{cycle_id, started_at, ended_at, top_notes: [...], summary, run_id}`.
- `data/current_cycle.json` — `{cycle_id, started_at, ends_at}`.
- `data/runs.json` — append-only-ish list of run records. Each: `{run_id, cycle_id, status, created_at, started_at, finished_at, agent_run_url, pr_url, artifact_path, error}`. Status enum: `queued | running | needs_merge | applying | applied | rejected | failed`. `needs_merge` = agent done, awaiting operator merge. `applying` = post-merge, lint+apply in progress. `applied` = artifact live. `rejected` = lint failed; last-good restored. `failed` = agent itself errored.
- `public/generated/theme.css` — currently-applied theme.
- `public/generated/slots.json` — currently-applied slot fragments `{slot_name: html_string}`.
- `public/generated/.last_good/` — copies of the previous accepted artifact, used by auto-revert.

Daily salt for `submitter_hash` lives in `data/salt.json`, rotated every UTC midnight by the worker.

## 5. API surface

Existing:
- `GET /api/notes` — list notes (extended with `votes` field).
- `POST /api/notes` — submit a post-it (gated, see §7).
- `PUT /api/notes/<id>` — author-only edit/move (gated by `submitter_hash` match).
- `GET /api/worker-status` — existing summary/countdown info.

New:
- `POST /api/notes/<id>/vote` — upvote a note (current cycle only; archived notes 404). Body `{pow: str}` for the proof-of-work nonce. Idempotent per `voter_hash`; second call from same hash unvotes.
- `GET /api/cycle/current` — current cycle id, ends_at, top notes preview.
- `GET /api/cycle/<id>` — archived cycle detail.
- `GET /api/runs` — public list of recent runs (last 10), with sanitized fields (no internal errors, no IPs).
- `GET /logs?token=…` — operator-only HTML page (token compared against `LOGS_TOKEN` env var). Renders run records (full detail) + log ring buffer. Plain HTML, no auth scaffolding beyond the token.

## 6. Cycle pipeline

Each cycle is N minutes (default 15, env-configurable):

1. **Open cycle** — write `current_cycle.json`.
2. **Accept submissions and votes** — for the duration.
3. **Close cycle** — at tick:
   - Snapshot current notes, pick top-K by votes (default K=10; ties broken by `createdAt`).
   - Summarize the K notes (existing word-frequency summarizer is the v1 placeholder; a Claude call slots in later behind the same interface).
   - Write the handoff JSON + markdown to `worker/copilot_handoff/`.
   - Call `agent.kick_off(handoff)` → `run_id`. Append a `runs.json` entry with `status=queued`.
   - Archive the snapshot to `data/cycles/<cycle_id>.json`.
   - Clear `notes.json` for the next cycle.
   - Open the next cycle.
4. **Run-queue poller** transitions the run through `running → needs_merge`. When the operator merges (real merge in v2; mock-merge button on `/logs` in v1), the poller picks it up, transitions to `applying`, fetches the artifact, runs lint+apply, then transitions to `applied` (success) or `rejected` (lint failed; last-good restored). On agent error before merge, status becomes `failed`.

The cycle thread does NOT wait for the agent. A long-running agent simply means the user sees `needs_merge` in the queue UI when the next cycle's countdown reaches zero — that's fine, queues can have multiple in-flight runs.

## 7. Anti-abuse

- **`submitter_hash`** = `sha256(client_ip + user_agent + daily_salt)`. Hex digest. Used for both submission quota and vote dedupe.
- **Submission quota:** 3 post-its per cycle per `submitter_hash`. Server tracks counts per cycle in memory + on disk.
- **Vote dedupe:** 1 vote per (note_id, voter_hash). Stored on the note itself.
- **Proof-of-work** on `POST /api/notes`: client must produce a nonce such that `sha256(challenge + nonce)` has `D` leading zero bits (default D=18, ~half a second on a laptop). Challenge is `cycle_id + submitter_hash + minute_bucket`. Verified server-side before write. Vote endpoint uses a smaller D (e.g., 14).
- **Content lint on submit:** reject empty / >500 chars / regex-matched prompt-injection patterns (`/ignore (all )?previous/i`, `/system prompt/i`, `/<\s*script/i`). Log soft hits to the ring buffer.
- **Generation-time defense:** the agent only ever sees the *summary*, never raw post-it text. Prompt injection has to survive being summarized first — a substantial firewall.

## 8. Agent integration (mocked)

Adapter interface (`agent.py`):

```python
class AgentAdapter(Protocol):
    is_mock: bool                                              # capability flag for mock-only UI paths
    def kick_off(self, handoff: Handoff) -> str: ...           # returns run_id; raises AgentError
    def poll(self, run_id: str) -> RunStatus: ...              # raises AgentError if unknown
    def fetch_artifact(self, run_id: str) -> Artifact: ...     # raises AgentError if not ready

@dataclass
class RunStatus:
    status: str          # queued | running | needs_merge | merged | failed
    detail: str = ""
    agent_run_url: str | None = None  # link to GitHub Actions run page
    pr_url: str | None = None         # link to the PR the agent opened
    error: str | None = None          # populated when status == "failed"

class AgentError(RuntimeError): ...

def make_agent() -> AgentAdapter:
    """Factory selected by AGENT_KIND env var; default 'mock'."""
```

Adapter selection is `agent.make_agent()`, not a hardcoded constructor — this is the swap seam between v1 (mock) and v2 (real GitHub).

`MockGithubAgent` (v1, `is_mock = True`):
- `kick_off`: synthesises a `run_id`, schedules an internal state machine: `queued (5s) → running (30s) → needs_merge (manual)`.
- The "manual merge" step in v1 is a button on the secret `/logs` page that signals "operator merged" via a mock-only `signal_merge(run_id)` method (NOT part of the Protocol). The poller then drives the run through `applying → applied / rejected` as in §6.
- `fetch_artifact`: returns a deterministic-but-varied canned artifact derived from the summary text (palette/font/seed hashed from summary, plus slot fragments that name the top topic). Plausible enough that watching the site mutate cycle-to-cycle is satisfying.
- `poll`: returns the current state from the in-memory state machine.

`GithubActionsAgent` (v1 skeleton, `is_mock = False`): all methods raise `NotImplementedError` in v1. The skeleton exists so the protocol is exercised structurally and `make_agent()` can return it under `AGENT_KIND=github`. Real wiring (workflow_dispatch, PR polling, artifact download) is its own v2 task. The `/logs` page swaps the mock-merge button for a "merge on GitHub" link when the adapter is non-mock.

**Robustness invariants** the poller enforces (independent of which adapter is in use):
- Stuck runs are timed out (`MAX_RUN_DURATION_SECONDS = 1h`) → marked `failed`.
- `kick_off` failures during `close_cycle` are caught and recorded as a `status=failed` run, so the cycle never silently drops.
- `applying` is treated as recoverable: a server crash mid-apply leaves a run in `applying`; the next poll re-fetches and re-applies (artifacts are deterministic for a given run, so this is safe).
- Adapters MUST be thread-safe: `kick_off` runs in the cycle worker thread, `poll`/`fetch_artifact` in the poller thread, `signal_merge` (mock-only) in HTTP handler threads.

## 9. Lint + apply

Output schema from agent: `{theme_css: str, slots: {name: html}}`.

Lint (deterministic, no model in the loop):
- HTML in slots: parse with `html.parser`, allowlist tags `{div, span, p, h1, h2, h3, h4, h5, h6, ul, ol, li, em, strong, br, hr, a, blockquote, code, pre, figure, figcaption}`, allowlist attrs `{class, href (must start with `#`)}`. Strip everything else.
- Reject if any `<script>`, `<iframe>`, `<object>`, `<embed>`, `<style>`, `<link>`, or `on*` attribute appears anywhere.
- CSS: regex-reject `@import`, `url\(\s*(?!['\"]?#|data:image/)`, `expression\s*\(`, `behavior\s*:`, `javascript:`. Allow `data:image/...` for embedded SVG/PNG inline backgrounds.
- Slot HTML and CSS each capped at 50 KB.

Apply:
- Write `public/generated/theme.css` and `public/generated/slots.json`.
- Run a smoke check: spawn a subprocess that does a headless GET (just `urllib`) of the homepage HTML and asserts the kernel marker strings (e.g., `id="new-note-btn"`, `id="big-clock"`) are still present in the response. (The real visual-render check is deferred; for v1 the kernel is server-rendered and not affected by the artifact, so the check is mostly defensive.)
- On any failure, copy `.last_good/` back into place; mark run `rejected` with reason.
- On success, copy current artifact into `.last_good/`.

## 10. Frontend changes

`public/app.js`:
- Notes render with size + glow scaling with `votes` (e.g., `transform: scale(1 + log(1+votes)/8)`).
- Click-to-vote on a note: small heart in the corner; one click = vote, second click = unvote (uses same `voter_hash`).
- Submit flow: opens a modal, runs proof-of-work in a Web Worker (don't block the main thread), POSTs.
- On load, fetches `/api/runs` and renders a small queue status pill in the kernel chrome (`current run: queued · ETA Xm`).
- Reads `public/generated/slots.json` (may 404 before the first cycle; fall back to defaults baked into HTML).
- A `?reset=1` query param (or button in the kernel) bypasses the generated theme + slots — escape hatch.

`public/index.html`:
- Add `data-slot="intro" / "aside" / "footer-extra"` divs.
- Add the queue status pill.
- Link `public/generated/theme.css` after the base `styles.css` so generated rules win.

## 11. Secret `/logs` page

- Route gated by `LOGS_TOKEN` env var. Missing or wrong token → 404 (not 403, to avoid advertising the route).
- Server-rendered HTML, no JS framework. Sections:
  - **Runs table:** every entry from `data/runs.json` with full detail — `agent_run_url`, `pr_url`, `error`, `artifact_path`, links to view the raw artifact.
  - **Manual-merge buttons** for runs in `needs_merge` state (v1 mock-merge interaction; in v2, the operator clicks "merge" in GitHub directly and this just shows status).
  - **Log ring buffer:** newest first, level + ts + message + structured fields. Clearable.
  - **Cycle history:** list of archived cycles with summary + top notes + which run was associated.
- No write actions other than the v1 mock-merge button and a "clear log buffer" button.

## 12. Testing strategy

- **Unit:**
  - `lint` — table-driven cases: each disallowed pattern + each allowed pattern.
  - `submitter_hash` and PoW verification.
  - `summarizer` — deterministic given input.
  - `MockGithubAgent` state machine transitions.
- **Integration:**
  - Full cycle with `MockGithubAgent`: submit notes, vote, close cycle, mock-merge run, assert `theme.css` + `slots.json` written, assert `cycles/<id>.json` archived, assert next cycle opened.
  - Vote idempotency across repeated requests with same `voter_hash`.
  - Quota enforcement: 4th submission within a cycle is rejected.
  - Auto-revert: feed an artifact that fails the smoke check, assert `.last_good/` restored.
- **Smoke (run via `python -m unittest`):** start the server in a thread, hit each public endpoint, assert shape. Hit `/logs` without token → 404; with token → 200.

## 13. File layout (after implementation)

```
server.py                # HTTP server + worker thread + queue poller
agent.py                 # AgentAdapter protocol + MockGithubAgent
lint.py                  # HTML/CSS lint + apply + auto-revert
storage.py               # JSON file helpers, locks, salt rotation
abuse.py                 # submitter_hash + PoW verification + quotas
logs.py                  # ring buffer + /logs HTML renderer
public/
  index.html             # kernel + soft-kernel + free-zone slots
  styles.css             # base styles (kernel)
  app.js                 # frontend incl. PoW worker
  pow-worker.js          # Web Worker for proof-of-work
  generated/
    theme.css            # written by apply
    slots.json           # written by apply
    .last_good/          # fallback
data/
  notes.json
  current_cycle.json
  cycles/
  runs.json
  salt.json
worker/copilot_handoff/  # existing, kept
docs/superpowers/specs/  # this file lives here
tests/
  test_lint.py
  test_abuse.py
  test_cycle_integration.py
  test_mock_agent.py
  test_endpoints.py
```

## 14. Future work (v2+)

- Replace `MockGithubAgent` with `GithubActionsAgent`. Add `GITHUB_TOKEN` env var, a workflow file, and a small CLI that runs the coding agent on the handoff.
- Real deploy on Hetzner VPS with auto-redeploy on `main` push.
- Optional sandboxed-iframe free zone (brainstorming option C) for richer agent expressiveness.
- Optional auto-merge with CI checks (lint + smoke + visual regression) gating.
- Replace word-frequency summarizer with a Claude call.
- Per-user identity (magic-link email) + persistent vote history.
