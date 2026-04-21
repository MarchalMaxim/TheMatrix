"""Tiny wrapper around GitHub's Contents API — used by the /admin file editor.

Separated from agent.py because it's a different lifecycle (server-side, hot
path, called per admin request) and the agent module already does a lot.
"""
from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request

_GITHUB_API = "https://api.github.com"


class GithubContentError(RuntimeError):
    """Raised on any GitHub Contents API failure."""


def _auth_headers() -> dict[str, str]:
    token = os.environ.get("MATRIX_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or ""
    if not token:
        raise GithubContentError("MATRIX_GITHUB_TOKEN / GITHUB_TOKEN not set")
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "TheMatrix-server/1.0",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def _repo_owner() -> str:
    owner = os.environ.get("GITHUB_OWNER", "")
    if not owner:
        raise GithubContentError("GITHUB_OWNER not set")
    return owner


def _repo_name() -> str:
    repo = os.environ.get("GITHUB_REPO", "")
    if not repo:
        raise GithubContentError("GITHUB_REPO not set")
    return repo


def _repo_ref() -> str:
    # Defaults to main; separate from GITHUB_REF used by the workflow dispatcher
    return os.environ.get("GITHUB_REF", "main")


def _request(method: str, path: str, body: dict | None = None) -> dict:
    url = f"{_GITHUB_API}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = _auth_headers()
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            return json.loads(raw.decode("utf-8")) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "ignore")[:300]
        except Exception:  # noqa: BLE001
            pass
        raise GithubContentError(f"GitHub API {method} {path}: HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise GithubContentError(f"GitHub API network error on {method} {path}: {exc}") from exc


def list_public_files() -> list[str]:
    """Return all blob paths under 'public/' on the ref branch, recursively."""
    owner, repo, ref = _repo_owner(), _repo_name(), _repo_ref()
    branch = _request("GET", f"/repos/{owner}/{repo}/branches/{ref}")
    tree_sha = branch.get("commit", {}).get("commit", {}).get("tree", {}).get("sha")
    if not tree_sha:
        raise GithubContentError(f"could not resolve tree sha for branch {ref}")
    tree = _request("GET", f"/repos/{owner}/{repo}/git/trees/{tree_sha}?recursive=1")
    files = [
        item.get("path", "")
        for item in tree.get("tree", [])
        if item.get("type") == "blob" and (item.get("path") or "").startswith("public/")
    ]
    return sorted(p for p in files if p)


def get_file(path: str) -> tuple[str, str]:
    """Fetch a file's current UTF-8 content and blob sha. Raises on error."""
    owner, repo, ref = _repo_owner(), _repo_name(), _repo_ref()
    data = _request("GET", f"/repos/{owner}/{repo}/contents/{path}?ref={ref}")
    content_b64 = (data.get("content") or "").replace("\n", "")
    try:
        content = base64.b64decode(content_b64).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as exc:
        raise GithubContentError(f"could not decode {path}: {exc}") from exc
    sha = data.get("sha") or ""
    return content, sha


def put_file(path: str, content: str, sha: str | None, message: str) -> dict:
    """Create or update a file on the ref branch. Returns the commit+content
    metadata from GitHub. If sha is None/empty, creates a new file; otherwise
    updates in place (sha must match GitHub's current blob sha for the file)."""
    owner, repo, ref = _repo_owner(), _repo_name(), _repo_ref()
    body: dict[str, str] = {
        "message": message,
        "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
        "branch": ref,
    }
    if sha:
        body["sha"] = sha
    return _request("PUT", f"/repos/{owner}/{repo}/contents/{path}", body)
