"""Chaos agent: rewrite files under public/ based on the cycle's top user prompts.

This runs inside the matrix-handoff GitHub Actions workflow. It:
  1. Reads every file currently under public/ (the stuff the agent is allowed to touch)
  2. Reads the cycle summary + top notes from env vars set by the workflow
  3. Calls the Anthropic API with the current files + cycle context
  4. Parses a <<<FILE:path>>> ... <<<END>>> delimited response
  5. Writes the new contents of each returned file back to disk (ONLY under public/)
  6. Prints what it changed so the workflow can log it

No theme.css / slots.json layering any more. The agent has full creative freedom
inside public/. The post-it CORE is preserved by telling Claude what the server's
API contract looks like and trusting it (plus: the user is OK with breakage and
manual revert).

Output format Claude must produce:

    <<<FILE:public/styles.css>>>
    ...new file contents...
    <<<END>>>

    <<<FILE:public/index.html>>>
    ...new file contents...
    <<<END>>>

Files that are not mentioned are left untouched. Any file path not starting
with "public/" is dropped as a safety net.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
MODEL = os.environ.get("ANTHROPIC_MODEL") or "claude-sonnet-4-5"
MAX_TOKENS = 8000

REPO_ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DIR = REPO_ROOT / "public"

# Files we never overwrite even if the agent returns them — these are machine-
# generated or not editable content (and would cause conflicts).
SKIP_PATHS = {
    "public/generated",        # old artifact mount point, if it still exists
}

# We include files as context up to this size to stay in token budget.
MAX_FILE_BYTES = 20_000

SYSTEM_PROMPT = """You are a creative chaos agent redesigning a whimsical web app called **TheMatrix**.

TheMatrix is a post-it-note wall where users paste ideas. Every 4 hours the top-voted \
ideas get summarised and handed to you, the agent. Your job is to rewrite the site so \
it reflects those ideas — in any artistic direction, no matter how strange, intense, \
or confrontational. Go wild. Be experimental. The user wants chaos, not safety.

HARD INVARIANTS — if you break these, the site dies and users can't post:

1. The frontend MUST keep calling these server endpoints:
   - GET    /api/notes              → list of notes (each has id, text, x, y, color, author_label, is_owner)
   - POST   /api/notes               → create note, body: {text, pow, challenge, x, y, color}
   - PUT    /api/notes/<id>          → move/edit, body: {x?, y?, text?}
   - DELETE /api/notes/<id>          → delete (owner only; server 403s otherwise)
   - GET    /api/pow-challenge       → {challenge, difficulty_submit, difficulty_vote}
   - GET    /api/worker-status       → {cycle_id, next_run_epoch, summary, ...}
   - GET    /api/cycle/current       → current cycle
   - POST   /api/notes/<id>/vote     → vote (requires PoW)
   - POST   /api/trigger-cycle       → dev button

2. The JS layer must spawn the PoW Web Worker via `new Worker("/pow-worker.js")` \
with `{challenge, difficulty}` payload; `pow-worker.js` must continue to exist \
and accept that message. Don't rewrite pow-worker.js unless you fully understand \
the SHA-256 leading-zero-bits algorithm it uses; the server verifies PoW identically.

3. The user must still be able to create a new post-it (click "+ new post-it" or \
equivalent), see all posted notes, drag them, edit their own, delete their own.

Everything else is yours: layout, colours, typography, animations, copy, extra \
decorative DOM, weird cursors, visual glitches, overlays, sound-less audio tags, \
custom fonts, wild backgrounds — go for it. Make the site feel like it came from \
a different dimension this cycle compared to last.

RESPONSE FORMAT — strict. Emit one or more blocks:

    <<<FILE:public/PATH>>>
    COMPLETE new file contents here. NOT a diff.
    <<<END>>>

Rules:
- Only rewrite files whose paths start with "public/".
- Emit FULL file contents for every file you change (no diffs, no placeholders).
- If a file should stay unchanged, do NOT include it in your response.
- No commentary outside the <<<FILE>>> blocks.
- Do NOT wrap contents in triple-backtick fences.
"""


def read_public_files() -> dict[str, str]:
    files: dict[str, str] = {}
    if not PUBLIC_DIR.is_dir():
        return files
    for path in sorted(PUBLIC_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(REPO_ROOT).as_posix()
        # Skip machine-generated / ephemeral files
        if any(rel.startswith(skip + "/") or rel == skip for skip in SKIP_PATHS):
            continue
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if len(data) > MAX_FILE_BYTES:
            # Too big to fit in the prompt — skip
            continue
        try:
            files[rel] = data.decode("utf-8")
        except UnicodeDecodeError:
            # Probably a binary asset; agent can't meaningfully edit it anyway
            continue
    return files


def build_user_message(summary: str, notes: list[dict], files: dict[str, str]) -> str:
    note_lines = "\n".join(
        f"- ({int(n.get('votes', 0))} votes) {(n.get('text') or '').strip()}"
        for n in notes
        if isinstance(n, dict) and (n.get("text") or "").strip()
    ) or "- (no prompts this cycle)"
    files_block = "\n\n".join(
        f"=== {path} ===\n{content}" for path, content in files.items()
    )
    return (
        f"CYCLE SUMMARY:\n{summary}\n\n"
        f"TOP USER PROMPTS THIS CYCLE:\n{note_lines}\n\n"
        f"CURRENT FILES UNDER public/ (you may rewrite any of these):\n\n"
        f"{files_block}\n\n"
        f"Now return your file rewrites in the <<<FILE:…>>>…<<<END>>> format."
    )


def call_anthropic(user_message: str) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    body = {
        "model": MODEL,
        "max_tokens": MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_message}],
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
    with urllib.request.urlopen(req, timeout=180) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    blocks = payload.get("content") or []
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


FILE_BLOCK_RE = re.compile(
    r"<<<FILE:(?P<path>[^\n>]+)>>>\r?\n(?P<content>.*?)\r?\n<<<END>>>",
    re.DOTALL,
)


def parse_file_blocks(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for match in FILE_BLOCK_RE.finditer(text):
        path = match.group("path").strip()
        content = match.group("content")
        if not path.startswith("public/"):
            print(f"[chaos] SKIP non-public path: {path!r}", file=sys.stderr)
            continue
        if any(path.startswith(skip + "/") or path == skip for skip in SKIP_PATHS):
            print(f"[chaos] SKIP protected path: {path!r}", file=sys.stderr)
            continue
        # Reject absolute / traversal paths
        if ".." in Path(path).parts or Path(path).is_absolute():
            print(f"[chaos] SKIP suspicious path: {path!r}", file=sys.stderr)
            continue
        out[path] = content
    return out


def write_file_blocks(blocks: dict[str, str]) -> list[str]:
    """Write each block to disk under REPO_ROOT. Returns list of written paths."""
    written: list[str] = []
    for rel, content in blocks.items():
        target = REPO_ROOT / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8", newline="\n")
        written.append(rel)
    return written


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

    files = read_public_files()
    if not files:
        print("[chaos] no files found under public/ — aborting", file=sys.stderr)
        return 1
    print(f"[chaos] loaded {len(files)} source files under public/")

    user_message = build_user_message(summary, notes, files)
    try:
        raw = call_anthropic(user_message)
    except (RuntimeError, urllib.error.URLError, urllib.error.HTTPError,
            TimeoutError) as exc:
        # In the old generator we had a deterministic fallback, but for the
        # chaos flow "no changes" is the right fallback — better than
        # corrupting the site with a stub.
        print(f"[chaos] API call failed ({type(exc).__name__}: {exc}); "
              f"no changes committed for handoff {handoff_id}", file=sys.stderr)
        return 0

    blocks = parse_file_blocks(raw)
    if not blocks:
        print(f"[chaos] no valid file blocks in response; raw[:300]={raw[:300]!r}",
              file=sys.stderr)
        return 0

    written = write_file_blocks(blocks)
    print(f"[chaos] handoff {handoff_id}: rewrote {len(written)} file(s):")
    for p in written:
        print(f"  - {p}")

    # Also record the cycle metadata so the server / future history view can
    # read it easily. Written inside public/ so it gets committed too.
    meta_dir = REPO_ROOT / "public" / "cycles"
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{handoff_id}.json").write_text(
        json.dumps({
            "handoff_id": handoff_id,
            "summary": summary,
            "notes": notes,
            "files_changed": written,
        }, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
