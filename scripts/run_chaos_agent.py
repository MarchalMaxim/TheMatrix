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
MAX_TOKENS_PER_TURN = 4000
MAX_ITERATIONS = 24
MAX_FILE_READ_BYTES = 80_000

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

You have four tools: `list_files`, `read_file`, `write_file`, `delete_file`, and one terminator: `finalize`.

## Suggested workflow

1. `list_files` on `public` to see what's there.
2. `read_file` on the files you intend to change (you often want to see the current state before rewriting).
3. Use `write_file` to land your changes. Write COMPLETE file contents, not diffs.
4. Optionally `delete_file` for files you want to remove (but never the CORE files — see below).
5. Call `finalize` with a one-line summary of what you did.

You can make multiple `write_file` calls across turns — think step by step.

## HARD INVARIANTS — breaking any of these breaks the site

1. The frontend MUST continue to call these server endpoints (they power the post-it flow):
   - GET    /api/notes, /api/pow-challenge, /api/worker-status, /api/cycle/current
   - POST   /api/notes (create, with {text, pow, challenge, x, y, color})
   - PUT    /api/notes/<id> (move/edit)
   - DELETE /api/notes/<id> (owner only)
   - POST   /api/notes/<id>/vote

2. The JS layer must spawn the PoW Web Worker via `new Worker("/pow-worker.js")` with `{challenge, difficulty}`. `pow-worker.js` must continue to exist and must not be broken — if you don't fully understand the SHA-256 leading-zero-bits algorithm inside it, leave it alone.

3. Users must still be able to: click "new post-it" → type text → see it appear; drag any note; edit their own; delete their own.

4. There MUST remain an inconspicuous link to /logs — e.g. `<footer id="site-footer"><a href="/logs" id="logs-link">…</a></footer>`. You can restyle, move, translate, themeify it — but the link to `/logs` must be present on the main page and visible.

5. There MUST NOT be a "trigger cycle" / "rupture now" / equivalent button on the public page. Cycle triggering is operator-only. Do not add one back, even thematically.

6. Do not rewrite anything outside `public/`. The tools enforce this but don't test it.

## Creative license

Everything else is yours. Rewrite colours, layout, typography, copy, language, text direction, animations, decorative DOM, custom fonts, wild backgrounds, alternate cursors, CSS filters, WebGL overlays, extra sections, extra images (inline SVG only), sounds via the Web Audio API — anything. Make the site feel like it came from a different dimension than last cycle.

Resist the temptation to be tasteful. The interesting cycles are the ones that commit to an aesthetic.
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
    with urllib.request.urlopen(req, timeout=300) as resp:
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
        f"Explore the current files under public/ with list_files and read_file, "
        f"then rewrite whatever you want with write_file. Call finalize when done."
    )


def run_agent_loop(summary: str, notes: list) -> dict:
    messages = [{"role": "user", "content": build_initial_message(summary, notes)}]
    written: set[str] = set()
    deleted: set[str] = set()
    finalized = False
    final_summary = ""

    for turn in range(MAX_ITERATIONS):
        print(f"[chaos] turn {turn + 1}/{MAX_ITERATIONS}", file=sys.stderr)
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
    if not outcome["finalized"]:
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
        }, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
