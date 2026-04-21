"""Chaos agent — multi-turn tool-use loop that rewrites the site each cycle.

Runs inside the matrix-handoff GitHub Actions workflow. The agent:

  1. Gets a system prompt describing hard invariants + creative freedom
  2. Gets a user message with the cycle summary + top notes
  3. Uses four tools to reshape files under public/:
       list_files  — see what's there
       read_file   — inspect specific contents
       write_file  — rewrite or create (under public/ only)
       delete_file — remove (under public/ only, never core files)
  4. Calls finalize() when done, with a short summary of the changes

The agent typically uses 5-15 turns per cycle — far more powerful than
the old single-call version, which had to fit everything into one big
response and rewrite complete files blindly.

Exit codes:
  0 — the agent made at least one change and finalized
  1 — public/ doesn't exist
  2 — API or network error (workflow fails)
  3 — agent finalized but made no changes (effectively a no-op cycle)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-5"
MAX_TOKENS_PER_TURN = 8000
MAX_ITERATIONS = 40
MAX_FILE_READ_BYTES = 120_000
FETCH_URL_MAX_BYTES = 40_000
FETCH_URL_TIMEOUT_SECONDS = 15

# Per-API-call timeout. Shorter than before (300s) so a single hung call
# can't blow the entire wall-clock budget.
ANTHROPIC_CALL_TIMEOUT = 120

# Hard wall-clock budget for the entire agent loop. If we hit this, we
# break out of the loop gracefully and let the commit step run on whatever
# files were already written. MUST be well below the workflow's job
# timeout-minutes so the commit step has time to finish.
WALL_CLOCK_BUDGET_SECONDS = int(os.environ.get("CHAOS_WALL_CLOCK_BUDGET") or 14 * 60)

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "public"

# Core files the agent can rewrite but not delete — removing any of these
# breaks the app hard.
CORE_FILES = {
    "public/index.html",
    "public/app.js",
    "public/styles.css",
    "public/pow-worker.js",
}

SYSTEM_PROMPT = """You are the **chaos agent** redesigning a web app called TheMatrix — a post-it-note wall where users paste ideas. Every 4 hours you inherit the site and the top-voted user prompts for the cycle; your job is to rewrite the site so it reflects those ideas, in any artistic direction, no matter how strange, intense, or confrontational. The user wants genuine chaos — not safety.

You have six tools plus a terminator: `list_files`, `read_file`, `write_file`, `delete_file`, `get_cycle_history`, `fetch_url`, and `finalize`.

## Suggested workflow

1. `get_cycle_history` FIRST — see what aesthetics have been used in the last few cycles. Your job is to make this cycle feel DIFFERENT from those. Chaos that repeats itself is boring.
2. `list_files` on `public` to see what's there.
3. `read_file` on the files you intend to change (you often want to see the current state before rewriting).
4. Optionally `fetch_url` any public URL for inspiration — Google Fonts CSS, a CDN's example page, docs for a library you want to reference. The response is truncated at 40KB and only used as REFERENCE — do NOT blindly paste fetched script tags pointing to arbitrary domains; use what you learn to write your own code. Private / localhost / metadata URLs are blocked.
5. Use `write_file` to land your changes. Write COMPLETE file contents, not diffs.
6. Optionally `delete_file` for files you want to remove (but never the CORE files — see below).
7. Call `finalize` with a one-line summary of what you did.

You can make multiple `write_file` calls across turns — think step by step.

## HARD INVARIANTS — breaking any of these breaks the site

1. The frontend MUST continue to call these server endpoints (they power the post-it flow):
   - GET    /api/notes, /api/pow-challenge, /api/worker-status, /api/cycle/current
   - GET    /api/cycles/previous    (returns {handoff_id, summary, agent_summary, notes:[…]})
   - POST   /api/notes (create, with {text, pow, challenge, x, y, color})
   - PUT    /api/notes/<id> (move/edit)
   - DELETE /api/notes/<id> (owner only)
   - POST   /api/notes/<id>/vote

2. The JS layer must spawn the PoW Web Worker via `new Worker("/pow-worker.js")` with `{challenge, difficulty}`. `pow-worker.js` must continue to exist and must not be broken — if you don't fully understand the SHA-256 leading-zero-bits algorithm inside it, leave it alone.

3. Users must still be able to: click "new post-it" → type text → see it appear; drag any note; edit their own; delete their own.

4. There MUST remain an inconspicuous link to /logs — e.g. `<footer id="site-footer"><a href="/logs" id="logs-link">…</a></footer>`. You can restyle, move, translate, themeify it — but the link to `/logs` must be present on the main page and visible.

5. There MUST NOT be a "trigger cycle" / "rupture now" / equivalent button on the public page. Cycle triggering is operator-only. Do not add one back, even thematically.

6. The index page MUST include a "previous cycle" preview section that shows users the prompt-summary and the post-its that fed the LAST cycle. The required DOM anchors are:
     <section id="previous-cycle" data-invariant="previous-cycle">
       <h2>…themed heading…</h2>
       <p id="prev-cycle-summary"></p>
       <details id="prev-cycle-details">
         <summary><span id="prev-cycle-count">0</span> <span>…themed noun…</span></summary>
         <ul id="prev-cycle-notes-list"></ul>
       </details>
     </section>
   You can restyle this section aggressively (copy, icons, fonts, borders, animations) but keep ALL the listed IDs exactly so `/app.js` can populate it from `/api/cycles/previous`. Don't move it inside a <template> and don't hide it with display:none.

7. Do not rewrite anything outside `public/`. The tools enforce this but don't test it.

## Creative license

Everything else is yours. Rewrite colours, layout, typography, copy, language, text direction, animations, decorative DOM, custom fonts, wild backgrounds, alternate cursors, CSS filters, WebGL overlays, extra sections, extra images (inline SVG only), sounds via the Web Audio API — anything. Make the site feel like it came from a different dimension than last cycle.

Resist the temptation to be tasteful. The interesting cycles are the ones that commit to an aesthetic.

## Scale up the canvas

Don't settle for a single-page site with two files. Go bigger each cycle:

- **Add new pages.** Create `public/manifesto.html`, `public/gallery.html`, `public/about.html`, `public/<whatever>.html` — as many as the aesthetic demands. Static files under `public/` are served directly by the server (e.g. `public/about.html` → `https://site/about.html`). A hero page that links out to 2-3 themed subpages is far more interesting than one long scroller.
  - **Crucial:** a new page is INVISIBLE unless you link to it. When you create a page, ALSO add a nav link / button / floating chip / themed menu / footer link on index.html (or another already-reachable page) so users can find it. An orphaned page is a wasted file.
  - Pages can have their own page-specific CSS file (e.g. `public/gallery.css`) — just `<link>` it in the new page's head.

- **Stack the DOM.** Index.html doesn't have to be minimal. Add multiple `<section>`s: lore, stats widgets, a running commentary from the "ghost of a past cycle," a scrollable gallery of inline SVG art, a sticky bar, a side panel, modal overlays, animated mascots. Layered pages with narrative depth outperform clean-but-empty ones.

- **Write JavaScript based on the post-its.** This is first-class, not decoration. If a post-it asks for "a pet cat that follows the cursor" — BUILD THAT: a new `public/cat.js`, a <canvas> or floating DOM element, mousemove handlers, animations. If it asks for "a countdown to my birthday" — build it. If it asks for "a mini snake game in the corner" — build it. If it asks for "a live ticker of random facts" — build it. Add new script files freely (`public/<feature>.js`) and `<script src>` them from index.html or from a new sub-page. You can modify `public/app.js` directly too. The only hard constraints are:
  - The post-it core calls in HARD INVARIANT 1 must still work (so don't break `createNewNote`, the PoW worker spawn, the PUT/DELETE handlers in `app.js`).
  - `pow-worker.js` must not be modified unless you understand SHA-256 leading-zero-bits.

  Everything else is fair game: canvas drawing, WebGL, Web Audio, `requestAnimationFrame` loops, `IntersectionObserver`-driven animations, `fetch`-ing your own endpoints, localStorage games, multi-page state, whatever the post-its inspire. Make it interactive. Make it do something.

- **Inline SVG illustrations.** You don't need image files. A `<svg viewBox="…">` inside the HTML can hold full illustrations, diagrams, creatures, patterns. Use them.

- **Commit to a visual language.** If the cycle's theme is "medieval scroll," make EVERYTHING medieval — parchment textures, Gothic serif all-caps, illuminated drop caps, margin decorations, icons that look like woodcuts. Half-finished aesthetics read as mistakes; committed ones read as art.

When in doubt: add a page, add a panel, add a script.
"""

TOOLS = [
    {
        "name": "list_files",
        "description": (
            "List files in a directory (paths relative to repo root). "
            "Default directory is 'public'. Only directories under the repo "
            "root are allowed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "directory": {
                    "type": "string",
                    "description": "Directory path relative to repo root. e.g. 'public' or 'public/cycles'.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "read_file",
        "description": (
            "Read a UTF-8 text file. Path relative to repo root. Returns "
            "{content, bytes} on success, {error} otherwise."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a text file under 'public/'. Pass the FULL "
            "new contents, not a diff. Creates parent dirs as needed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path under public/, e.g. 'public/index.html'."},
                "content": {"type": "string", "description": "Complete UTF-8 file contents."},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "delete_file",
        "description": (
            "Delete a file under 'public/'. Forbidden on core files "
            "(index.html, app.js, styles.css, pow-worker.js)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
            },
            "required": ["path"],
        },
    },
    {
        "name": "fetch_url",
        "description": (
            "Fetch the first 40KB of a public URL (http or https) for "
            "inspiration — e.g. a Google Fonts CSS, a CDN file, a public "
            "snippet page, docs for a library you might use. Returns "
            "{content, content_type, bytes, truncated}. Do not trust "
            "fetched content as code-to-embed; only use it as REFERENCE. "
            "Private / localhost / metadata URLs are blocked."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL, e.g. https://fonts.googleapis.com/css2?family=Cinzel"},
            },
            "required": ["url"],
        },
    },
    {
        "name": "get_cycle_history",
        "description": (
            "Return metadata for the N most recent past cycles (summary, "
            "agent_summary, note_count, files_written, handoff_id). Use this "
            "at the start to AVOID REPEATING a recent aesthetic — the whole "
            "point of chaos is that each cycle feels different from the last."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "How many past cycles to return (default 5, max 20).",
                },
            },
            "required": [],
        },
    },
    {
        "name": "finalize",
        "description": (
            "Call ONCE when you've made all changes for this cycle. "
            "After this the agent loop exits and the changes are committed."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One-line summary of what you changed this cycle.",
                },
            },
            "required": ["summary"],
        },
    },
]


# ---------------------------------------------------------------------------
# Tool implementations
# ---------------------------------------------------------------------------

def _is_within(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def tool_list_files(directory: str = "public") -> dict:
    if ".." in Path(directory).parts:
        return {"error": "path traversal forbidden"}
    base = (REPO_ROOT / directory).resolve()
    if not _is_within(REPO_ROOT, base):
        return {"error": "directory outside repo root"}
    if not base.is_dir():
        return {"error": f"not a directory: {directory}"}
    files = []
    for p in sorted(base.rglob("*")):
        if p.is_file():
            files.append(p.relative_to(REPO_ROOT).as_posix())
    return {"files": files, "count": len(files)}


def tool_read_file(path: str) -> dict:
    if ".." in Path(path).parts:
        return {"error": "path traversal forbidden"}
    target = (REPO_ROOT / path).resolve()
    if not _is_within(REPO_ROOT, target):
        return {"error": "path outside repo root"}
    if not target.is_file():
        return {"error": f"not a file: {path}"}
    try:
        data = target.read_bytes()
    except OSError as exc:
        return {"error": f"read failed: {exc}"}
    if len(data) > MAX_FILE_READ_BYTES:
        return {"error": f"file too large ({len(data)} bytes > {MAX_FILE_READ_BYTES})"}
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        return {"error": "file is not UTF-8 text"}
    return {"content": content, "bytes": len(data)}


def tool_write_file(path: str, content: str) -> dict:
    if not path.startswith("public/"):
        return {"error": "writes only allowed under public/"}
    if ".." in Path(path).parts:
        return {"error": "path traversal forbidden"}
    target = (REPO_ROOT / path).resolve()
    if not _is_within(PUBLIC_DIR, target):
        return {"error": "path escapes public/"}
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    return {"ok": True, "bytes_written": len(content)}


def _is_blocked_host(host: str) -> bool:
    """Block SSRF-unsafe hosts: localhost, RFC1918, link-local, metadata."""
    import ipaddress
    host = (host or "").lower().strip()
    if not host:
        return True
    if host in {"localhost", "ip6-localhost", "ip6-loopback"}:
        return True
    # Strip brackets from IPv6 like "[::1]"
    host_clean = host.strip("[]")
    try:
        ip = ipaddress.ip_address(host_clean)
    except ValueError:
        # It's a hostname. We can't resolve it cheaply here; rely on the
        # runner being ephemeral + public-internet-only for practical safety.
        # Still block obvious names that resolve to metadata endpoints.
        if host_clean in {
            "metadata", "metadata.google.internal",
            "metadata.aws.internal",
        }:
            return True
        return False
    # IP address: block loopback / private / link-local / metadata
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast:
        return True
    # Explicit cloud metadata addresses
    if str(ip) in {"169.254.169.254", "fd00:ec2::254"}:
        return True
    return False


def tool_fetch_url(url: str) -> dict:
    """Fetch a public URL and return up to FETCH_URL_MAX_BYTES of its body as text."""
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return {"error": "only http(s) URLs allowed"}
    try:
        from urllib.parse import urlparse
        parsed = urlparse(url)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"could not parse URL: {exc}"}
    host = (parsed.hostname or "")
    if _is_blocked_host(host):
        return {"error": f"host {host!r} is blocked (private / metadata / localhost)"}
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "TheMatrix-chaos-agent/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=FETCH_URL_TIMEOUT_SECONDS) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read(FETCH_URL_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}"}
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        return {"error": f"{type(exc).__name__}: {exc}"}
    truncated = len(raw) > FETCH_URL_MAX_BYTES
    body = raw[:FETCH_URL_MAX_BYTES]
    try:
        text = body.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = body.decode("latin-1")
        except UnicodeDecodeError:
            return {"error": "response body is not text-decodable"}
    return {
        "content": text,
        "content_type": content_type,
        "bytes": len(body),
        "truncated": truncated,
    }


def tool_get_cycle_history(limit: int = 5) -> dict:
    """Return metadata for the most recent N past cycles.

    Reads public/cycles/*.json (the per-cycle metadata the agent writes at the
    end of each run). Sorted newest-first by mtime. Does NOT include the full
    notes array — that would bloat the tool response; the summary + agent
    summary are enough to recognise and differentiate from past aesthetics.
    """
    limit = max(1, min(int(limit or 5), 20))
    cycles_dir = PUBLIC_DIR / "cycles"
    if not cycles_dir.is_dir():
        return {"cycles": [], "note": "no cycles directory yet"}
    files = sorted(cycles_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    out = []
    for f in files[:limit]:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append({
            "handoff_id": data.get("handoff_id"),
            "summary": (data.get("summary") or "")[:300],
            "agent_summary": (data.get("agent_summary") or "")[:300],
            "note_count": len(data.get("notes") or []),
            "files_written": (data.get("files_written") or [])[:20],
        })
    return {"cycles": out, "count": len(out)}


def tool_delete_file(path: str) -> dict:
    if not path.startswith("public/"):
        return {"error": "deletes only allowed under public/"}
    if ".." in Path(path).parts:
        return {"error": "path traversal forbidden"}
    if path in CORE_FILES:
        return {"error": f"refusing to delete core file: {path}"}
    target = (REPO_ROOT / path).resolve()
    if not _is_within(PUBLIC_DIR, target):
        return {"error": "path escapes public/"}
    if not target.is_file():
        return {"error": f"not a file: {path}"}
    target.unlink()
    return {"ok": True}


def dispatch_tool(name: str, args: dict, written: set, deleted: set) -> dict:
    try:
        if name == "list_files":
            return tool_list_files(args.get("directory") or "public")
        if name == "read_file":
            return tool_read_file(args["path"])
        if name == "write_file":
            res = tool_write_file(args["path"], args["content"])
            if res.get("ok"):
                written.add(args["path"])
            return res
        if name == "delete_file":
            res = tool_delete_file(args["path"])
            if res.get("ok"):
                deleted.add(args["path"])
                written.discard(args["path"])
            return res
        if name == "get_cycle_history":
            return tool_get_cycle_history(args.get("limit") or 5)
        if name == "fetch_url":
            return tool_fetch_url(args["url"])
        if name == "finalize":
            return {"ok": True}
        return {"error": f"unknown tool: {name}"}
    except KeyError as exc:
        return {"error": f"missing required argument: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Anthropic API call
# ---------------------------------------------------------------------------

def anthropic_call(messages: list) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    body = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS_PER_TURN,
        "system": SYSTEM_PROMPT,
        "tools": TOOLS,
        "messages": messages,
    }
    req = urllib.request.Request(
        ANTHROPIC_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=ANTHROPIC_CALL_TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Agent loop
# ---------------------------------------------------------------------------

def build_initial_message(summary: str, notes: list) -> str:
    note_lines = "\n".join(
        f"- ({int(n.get('votes', 0))} votes) {(n.get('text') or '').strip()}"
        for n in notes
        if isinstance(n, dict) and (n.get("text") or "").strip()
    ) or "- (no user prompts this cycle — you're free to just evolve the aesthetic)"
    return (
        f"CYCLE SUMMARY:\n{summary}\n\n"
        f"TOP USER PROMPTS (prioritise the ones with more votes):\n{note_lines}\n\n"
        f"Read those prompts LITERALLY. If someone asks for a pet cat that "
        f"follows the cursor, a countdown timer, a mini game, a sound-reactive "
        f"visualisation, a second page, a dropdown of haikus — BUILD IT. Write "
        f"JavaScript. Add new HTML pages. Add new JS files. Link them. The tools "
        f"let you create arbitrary files under public/.\n\n"
        f"Workflow: start with `get_cycle_history` to avoid repeating the last "
        f"few aesthetics. Then `list_files` and `read_file` to understand the "
        f"current state. Then `write_file` freely — new pages, new scripts, "
        f"modified index.html/app.js/styles.css. Call `finalize` when done."
    )


def run_agent_loop(summary: str, notes: list) -> dict:
    import time as _time
    messages = [{"role": "user", "content": build_initial_message(summary, notes)}]
    written: set[str] = set()
    deleted: set[str] = set()
    finalized = False
    final_summary = ""
    budget_hit = False
    started_at = _time.monotonic()

    for turn in range(MAX_ITERATIONS):
        elapsed = _time.monotonic() - started_at
        if elapsed > WALL_CLOCK_BUDGET_SECONDS:
            print(f"[chaos] WALL-CLOCK BUDGET HIT after {elapsed:.0f}s "
                  f"(budget={WALL_CLOCK_BUDGET_SECONDS}s) — committing partial work",
                  file=sys.stderr)
            budget_hit = True
            break
        print(f"[chaos] turn {turn + 1}/{MAX_ITERATIONS} "
              f"(elapsed={elapsed:.0f}s / {WALL_CLOCK_BUDGET_SECONDS}s)",
              file=sys.stderr)
        response = anthropic_call(messages)
        assistant_blocks = response.get("content", [])
        messages.append({"role": "assistant", "content": assistant_blocks})

        # Log any text the model produced (useful for debugging its reasoning)
        for b in assistant_blocks:
            if b.get("type") == "text":
                text = (b.get("text") or "").strip()
                if text:
                    # Truncate individual log lines but preserve all
                    print(f"[chaos]   said: {text[:300]!r}", file=sys.stderr)

        tool_uses = [b for b in assistant_blocks if b.get("type") == "tool_use"]
        if not tool_uses:
            # Model is done but didn't call finalize — accept and exit
            print("[chaos] response contained no tool_use; stopping", file=sys.stderr)
            break

        tool_results = []
        for tu in tool_uses:
            name = tu.get("name", "")
            args = tu.get("input") or {}
            # One-line summary of the tool call for log readability
            if name in ("read_file", "write_file", "delete_file"):
                path = args.get("path", "?")
                extra = f" ({args.get('bytes_written', len(args.get('content','')))}B)" if name == "write_file" else ""
                print(f"[chaos]   call: {name}({path}){extra}", file=sys.stderr)
            elif name == "list_files":
                print(f"[chaos]   call: list_files({args.get('directory') or 'public'})", file=sys.stderr)
            elif name == "finalize":
                print(f"[chaos]   call: finalize({args.get('summary', '')!r})", file=sys.stderr)
            else:
                print(f"[chaos]   call: {name}(...)", file=sys.stderr)

            result = dispatch_tool(name, args, written, deleted)
            if "error" in result:
                print(f"[chaos]     -> error: {result['error']}", file=sys.stderr)

            if name == "finalize":
                finalized = True
                final_summary = args.get("summary", "")

            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tu.get("id"),
                "content": json.dumps(result),
            })

        messages.append({"role": "user", "content": tool_results})

        if finalized:
            print("[chaos] agent finalized — exiting loop", file=sys.stderr)
            break
    else:
        print(f"[chaos] hit MAX_ITERATIONS={MAX_ITERATIONS} — forcing exit", file=sys.stderr)

    return {
        "written": sorted(written),
        "deleted": sorted(deleted),
        "final_summary": final_summary,
        "finalized": finalized,
        "budget_hit": budget_hit,
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def main() -> int:
    summary = (os.environ.get("SUMMARY") or "no summary").strip()
    notes_json = os.environ.get("NOTES_JSON") or "[]"
    handoff_id = os.environ.get("HANDOFF_ID") or "unknown"
    try:
        notes = json.loads(notes_json)
        if not isinstance(notes, list):
            notes = []
    except json.JSONDecodeError:
        notes = []

    if not PUBLIC_DIR.is_dir():
        print("[chaos] public/ directory not found — aborting", file=sys.stderr)
        return 1

    print(f"[chaos] starting handoff {handoff_id} (model={MODEL})", file=sys.stderr)

    try:
        outcome = run_agent_loop(summary, notes)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "ignore")[:500]
        except Exception:  # noqa: BLE001
            pass
        print(f"[chaos] FATAL HTTP {exc.code} from Anthropic: {detail}", file=sys.stderr)
        return 2
    except (RuntimeError, urllib.error.URLError, TimeoutError, OSError) as exc:
        print(f"[chaos] FATAL API error ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 2

    written, deleted = outcome["written"], outcome["deleted"]
    if not written and not deleted:
        print("[chaos] agent made no file changes — nothing to commit", file=sys.stderr)
        return 3

    print(f"[chaos] handoff {handoff_id}: {len(written)} written, {len(deleted)} deleted")
    for p in written:
        print(f"  [+] {p}")
    for p in deleted:
        print(f"  [-] {p}")
    if outcome["final_summary"]:
        print(f"[chaos] summary: {outcome['final_summary']}")
    if outcome.get("budget_hit"):
        print(f"[chaos] NOTE: wall-clock budget hit before finalize — "
              f"committing whatever was written", file=sys.stderr)
    elif not outcome["finalized"]:
        print("[chaos] NOTE: agent did not call finalize — changes committed anyway",
              file=sys.stderr)

    # Cycle metadata for the history view
    meta_dir = REPO_ROOT / "public" / "cycles"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{handoff_id}.json").write_text(
        json.dumps({
            "handoff_id": handoff_id,
            "summary": summary,
            "agent_summary": outcome["final_summary"],
            "notes": notes,
            "files_written": written,
            "files_deleted": deleted,
            "budget_hit": bool(outcome.get("budget_hit")),
            "finalized": bool(outcome.get("finalized")),
        }, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
