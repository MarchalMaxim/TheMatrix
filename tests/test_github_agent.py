"""Unit tests for GithubActionsAgent — HTTP layer is faked so no network."""
import io
import json
import os
import unittest
import urllib.error
import zipfile
from unittest import mock

import agent


class _FakeResponse:
    def __init__(self, status: int, body: bytes):
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


class _FakeHttp:
    """Records requests; replies from a scripted queue keyed by URL substring."""

    def __init__(self, scripts):
        # scripts: list of (url_substring, status, body_bytes) consumed in order
        self.scripts = list(scripts)
        self.calls: list[tuple[str, str]] = []  # (method, url)

    def __call__(self, request, timeout=None):  # noqa: ARG002
        url = request.full_url
        method = request.get_method()
        self.calls.append((method, url))
        if not self.scripts:
            raise AssertionError(f"unexpected HTTP call {method} {url}")
        sub, status, body = self.scripts.pop(0)
        if sub not in url:
            raise AssertionError(
                f"expected URL containing {sub!r}, got {url!r}"
            )
        if status >= 400:
            raise urllib.error.HTTPError(url, status, "err", {}, io.BytesIO(b""))
        return _FakeResponse(status, body)


def _make_agent(scripts):
    env = {
        "GITHUB_TOKEN": "tok",
        "GITHUB_OWNER": "octo",
        "GITHUB_REPO": "demo",
        "GITHUB_WORKFLOW_FILE": "matrix-handoff.yml",
        "GITHUB_REF": "main",
    }
    fake = _FakeHttp(scripts)
    with mock.patch.dict(os.environ, env, clear=False):
        a = agent.GithubActionsAgent(http_open=fake)
    return a, fake


def _zip_artifact(css: str, slots: dict) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        if css is not None:
            zf.writestr("theme.css", css)
        if slots is not None:
            zf.writestr("slots.json", json.dumps(slots))
    return buf.getvalue()


class GithubAgentInitTests(unittest.TestCase):
    def test_missing_env_raises(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(agent.AgentError):
                agent.GithubActionsAgent()


class GithubAgentKickOffTests(unittest.TestCase):
    def test_kick_off_dispatches_workflow_and_returns_handoff_id(self):
        a, fake = _make_agent([
            ("/actions/workflows/matrix-handoff.yml/dispatches", 204, b""),
        ])
        run_id = a.kick_off({"summary": "hi", "top_topics": [], "notes": [{"text": "be playful"}]})
        self.assertIsInstance(run_id, str)
        self.assertEqual(len(run_id), 12)  # uuid hex truncated
        self.assertEqual(len(fake.calls), 1)
        method, url = fake.calls[0]
        self.assertEqual(method, "POST")
        self.assertIn("/actions/workflows/matrix-handoff.yml/dispatches", url)

    def test_kick_off_propagates_http_errors(self):
        a, _ = _make_agent([
            ("/dispatches", 422, b""),
        ])
        with self.assertRaises(agent.AgentError):
            a.kick_off({"summary": "x", "top_topics": [], "notes": []})


class GithubAgentPollTests(unittest.TestCase):
    def _runs_response(self, handoff_id: str, status: str, conclusion: str | None,
                      run_id: int = 12345):
        return json.dumps({
            "workflow_runs": [{
                "id": run_id,
                "name": f"matrix-handoff-{handoff_id}",
                "status": status,
                "conclusion": conclusion,
                "html_url": f"https://github.com/octo/demo/actions/runs/{run_id}",
            }],
        }).encode()

    def test_queued_when_no_run_yet(self):
        a, _ = _make_agent([
            ("/runs", 200, json.dumps({"workflow_runs": []}).encode()),
        ])
        status = a.poll("abc123")
        self.assertEqual(status.status, "queued")

    def test_running_for_in_progress(self):
        a, _ = _make_agent([
            ("/runs", 200, self._runs_response("abc", "in_progress", None)),
        ])
        status = a.poll("abc")
        self.assertEqual(status.status, "running")
        self.assertIn("github.com", status.agent_run_url)

    def test_merged_when_completed_success(self):
        a, _ = _make_agent([
            ("/runs", 200, self._runs_response("abc", "completed", "success")),
        ])
        status = a.poll("abc")
        self.assertEqual(status.status, "merged")

    def test_failed_when_completed_failure(self):
        a, _ = _make_agent([
            ("/runs", 200, self._runs_response("abc", "completed", "failure")),
        ])
        status = a.poll("abc")
        self.assertEqual(status.status, "failed")
        self.assertIn("failure", status.error or "")


class GithubAgentFetchArtifactTests(unittest.TestCase):
    def _runs(self, handoff_id, conclusion="success"):
        return json.dumps({
            "workflow_runs": [{
                "id": 999,
                "name": f"matrix-handoff-{handoff_id}",
                "status": "completed",
                "conclusion": conclusion,
                "html_url": "https://github.com/octo/demo/actions/runs/999",
            }],
        }).encode()

    def test_fetch_raises_when_run_not_complete(self):
        runs = json.dumps({"workflow_runs": [{
            "id": 5, "name": "matrix-handoff-abc",
            "status": "in_progress", "conclusion": None,
            "html_url": "x",
        }]}).encode()
        a, _ = _make_agent([("/runs", 200, runs)])
        with self.assertRaises(agent.AgentError):
            a.fetch_artifact("abc")

    def test_fetch_raises_when_no_artifacts(self):
        a, _ = _make_agent([
            ("/runs", 200, self._runs("abc")),
            ("/runs/999/artifacts", 200, json.dumps({"artifacts": []}).encode()),
        ])
        with self.assertRaises(agent.AgentError):
            a.fetch_artifact("abc")

    def test_fetch_follows_302_to_azure_without_auth_header(self):
        """The /artifacts/{id}/zip endpoint redirects to Azure Blob; we must
        re-request the Location with no GitHub Authorization header."""
        zip_bytes = _zip_artifact("body{color:green}", {"intro": "<p>x</p>",
                                                         "aside": "<p>y</p>",
                                                         "footer-extra": "<p>z</p>"})
        azure_url = "https://pipelines.actions.githubusercontent.com/blob/abc?sig=xyz"

        # We need to inject the no-redirect opener path too. The first call
        # (GitHub side) goes through urllib.request.build_opener — we patch
        # that to return a fake opener that raises HTTPError(302). The second
        # call (Azure side) goes through self._http_open.
        a, fake = _make_agent([
            ("/runs", 200, json.dumps({"workflow_runs": [{
                "id": 999, "name": "matrix-handoff-abc",
                "status": "completed", "conclusion": "success",
                "html_url": "https://x",
            }]}).encode()),
            ("/runs/999/artifacts", 200, json.dumps({
                "artifacts": [{"id": 7, "name": "matrix-abc"}]
            }).encode()),
            (azure_url, 200, zip_bytes),  # Azure call goes through _http_open
        ])

        # Fake the GitHub-side opener to raise HTTPError(302)
        class _FakeRedirectOpener:
            def open(self, req, timeout=None):  # noqa: ARG002
                import io as _io
                raise urllib.error.HTTPError(
                    req.full_url, 302, "Found",
                    {"Location": azure_url}, _io.BytesIO(b"")
                )

        with mock.patch.object(
            agent.urllib.request, "build_opener",
            return_value=_FakeRedirectOpener(),
        ):
            art = a.fetch_artifact("abc")

        self.assertEqual(art["theme_css"], "body{color:green}")
        # Verify the Azure call went out WITHOUT a GitHub Authorization header
        azure_calls = [c for c in fake.calls if azure_url in c[1]]
        self.assertEqual(len(azure_calls), 1)

    def test_fetch_raises_on_bad_zip(self):
        azure_url = "https://blob.example/x"
        a, _ = _make_agent([
            ("/runs", 200, self._runs("abc")),
            ("/runs/999/artifacts", 200, json.dumps({
                "artifacts": [{"id": 7, "name": "x"}]
            }).encode()),
            (azure_url, 200, b"not a zip"),
        ])

        class _FakeRedirectOpener:
            def open(self, req, timeout=None):  # noqa: ARG002
                import io as _io
                raise urllib.error.HTTPError(
                    req.full_url, 302, "Found",
                    {"Location": azure_url}, _io.BytesIO(b"")
                )

        with mock.patch.object(
            agent.urllib.request, "build_opener",
            return_value=_FakeRedirectOpener(),
        ):
            with self.assertRaises(agent.AgentError):
                a.fetch_artifact("abc")


class MakeAgentTests(unittest.TestCase):
    def test_make_agent_github(self):
        env = {"AGENT_KIND": "github", "GITHUB_TOKEN": "t",
               "GITHUB_OWNER": "o", "GITHUB_REPO": "r"}
        with mock.patch.dict(os.environ, env, clear=False):
            a = agent.make_agent()
        self.assertIsInstance(a, agent.GithubActionsAgent)
        self.assertFalse(a.is_mock)


if __name__ == "__main__":
    unittest.main()
