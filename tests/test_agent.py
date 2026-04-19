import os
import unittest
import time
from unittest import mock

import agent


def _handoff(summary="x", topics=None):
    return {
        "summary": summary,
        "top_topics": topics or [],
        "notes": [],
    }


class MockAgentTests(unittest.TestCase):
    def setUp(self):
        self.agent = agent.MockGithubAgent(
            queued_seconds=0.05,
            running_seconds=0.05,
        )

    def test_is_mock_property(self):
        self.assertTrue(self.agent.is_mock)

    def test_kick_off_returns_run_id(self):
        run_id = self.agent.kick_off(_handoff())
        self.assertTrue(isinstance(run_id, str))
        self.assertTrue(run_id)

    def test_run_progresses_through_states(self):
        run_id = self.agent.kick_off(_handoff("make it pink", ["pink"]))
        self.assertEqual(self.agent.poll(run_id).status, "queued")
        time.sleep(0.06)
        self.assertEqual(self.agent.poll(run_id).status, "running")
        time.sleep(0.06)
        self.assertEqual(self.agent.poll(run_id).status, "needs_merge")

    def test_run_status_carries_urls(self):
        run_id = self.agent.kick_off(_handoff("x"))
        time.sleep(0.12)
        status = self.agent.poll(run_id)
        # mock fills these with placeholder/null values for protocol completeness
        self.assertTrue(hasattr(status, "agent_run_url"))
        self.assertTrue(hasattr(status, "pr_url"))
        self.assertTrue(hasattr(status, "error"))

    def test_signal_merge_unblocks_artifact(self):
        run_id = self.agent.kick_off(_handoff("make it green", ["green"]))
        time.sleep(0.15)
        self.assertEqual(self.agent.poll(run_id).status, "needs_merge")
        self.agent.signal_merge(run_id)
        self.assertEqual(self.agent.poll(run_id).status, "merged")
        artifact = self.agent.fetch_artifact(run_id)
        self.assertIn("theme_css", artifact)
        self.assertIn("slots", artifact)
        self.assertIsInstance(artifact["theme_css"], str)
        self.assertIsInstance(artifact["slots"], dict)

    def test_artifact_varies_with_summary(self):
        a_id = self.agent.kick_off(_handoff("make it pink", ["pink"]))
        b_id = self.agent.kick_off(_handoff("make it green", ["green"]))
        time.sleep(0.15)
        self.agent.signal_merge(a_id)
        self.agent.signal_merge(b_id)
        a = self.agent.fetch_artifact(a_id)
        b = self.agent.fetch_artifact(b_id)
        self.assertNotEqual(a["theme_css"], b["theme_css"])

    def test_unknown_run_id_raises_agent_error(self):
        with self.assertRaises(agent.AgentError):
            self.agent.poll("nope")
        with self.assertRaises(agent.AgentError):
            self.agent.fetch_artifact("nope")


class FactoryTests(unittest.TestCase):
    def test_default_kind_is_mock(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("AGENT_KIND", None)
            adapter = agent.make_agent()
            self.assertTrue(adapter.is_mock)

    def test_kind_mock_returns_mock(self):
        with mock.patch.dict(os.environ, {"AGENT_KIND": "mock"}):
            adapter = agent.make_agent()
            self.assertTrue(adapter.is_mock)

    def test_kind_github_returns_github_adapter(self):
        env = {"AGENT_KIND": "github", "GITHUB_TOKEN": "t",
               "GITHUB_OWNER": "o", "GITHUB_REPO": "r"}
        with mock.patch.dict(os.environ, env, clear=False):
            adapter = agent.make_agent()
            self.assertFalse(adapter.is_mock)
            self.assertIsInstance(adapter, agent.GithubActionsAgent)

    def test_unknown_kind_raises(self):
        with mock.patch.dict(os.environ, {"AGENT_KIND": "weird"}):
            with self.assertRaises(agent.AgentError):
                agent.make_agent()


# Note: Real behaviour of GithubActionsAgent (kick_off / poll / fetch_artifact
# with mocked HTTP) lives in tests/test_github_agent.py.


class FixesTests(unittest.TestCase):
    def setUp(self):
        self.agent = agent.MockGithubAgent(queued_seconds=0.01, running_seconds=0.01)

    def test_blank_agent_kind_uses_mock(self):
        with mock.patch.dict(os.environ, {"AGENT_KIND": ""}):
            adapter = agent.make_agent()
            self.assertTrue(adapter.is_mock)

    def test_whitespace_agent_kind_uses_mock(self):
        with mock.patch.dict(os.environ, {"AGENT_KIND": "  "}):
            adapter = agent.make_agent()
            self.assertTrue(adapter.is_mock)

    def test_mixed_case_agent_kind_resolved(self):
        with mock.patch.dict(os.environ, {"AGENT_KIND": "  MOCK  "}):
            adapter = agent.make_agent()
            self.assertTrue(adapter.is_mock)

    def test_run_status_carries_placeholder_urls(self):
        run_id = self.agent.kick_off({"summary": "x", "top_topics": [], "notes": []})
        status = self.agent.poll(run_id)
        self.assertIsNotNone(status.agent_run_url)
        self.assertIn(run_id, status.agent_run_url)

    def test_fetch_artifact_before_merge_raises(self):
        run_id = self.agent.kick_off({"summary": "x", "top_topics": [], "notes": []})
        time.sleep(0.05)
        # poll says needs_merge, but no signal_merge yet -> fetch must reject
        self.assertEqual(self.agent.poll(run_id).status, "needs_merge")
        with self.assertRaises(agent.AgentError):
            self.agent.fetch_artifact(run_id)

    def test_concurrent_kickoff_poll_merge_no_errors(self):
        """Stress test: many threads driving a few runs through full lifecycle."""
        import concurrent.futures
        agent_ = agent.MockGithubAgent(queued_seconds=0.0, running_seconds=0.0)

        def lifecycle(i):
            rid = agent_.kick_off({"summary": f"s{i}", "top_topics": [], "notes": []})
            for _ in range(5):
                agent_.poll(rid)
            agent_.signal_merge(rid)
            agent_.signal_merge(rid)  # idempotent
            artifact = agent_.fetch_artifact(rid)
            return artifact["theme_css"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
            results = list(ex.map(lifecycle, range(40)))
        self.assertEqual(len(results), 40)
        for css in results:
            self.assertGreater(len(css), 0)


if __name__ == "__main__":
    unittest.main()
