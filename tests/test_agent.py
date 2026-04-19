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

    def test_kind_github_returns_github_skeleton(self):
        with mock.patch.dict(os.environ, {"AGENT_KIND": "github"}):
            adapter = agent.make_agent()
            self.assertFalse(adapter.is_mock)
            self.assertIsInstance(adapter, agent.GithubActionsAgent)

    def test_unknown_kind_raises(self):
        with mock.patch.dict(os.environ, {"AGENT_KIND": "weird"}):
            with self.assertRaises(agent.AgentError):
                agent.make_agent()


class GithubActionsSkeletonTests(unittest.TestCase):
    def test_kick_off_not_implemented(self):
        adapter = agent.GithubActionsAgent()
        with self.assertRaises(NotImplementedError):
            adapter.kick_off(_handoff())

    def test_poll_not_implemented(self):
        adapter = agent.GithubActionsAgent()
        with self.assertRaises(NotImplementedError):
            adapter.poll("any")

    def test_fetch_artifact_not_implemented(self):
        adapter = agent.GithubActionsAgent()
        with self.assertRaises(NotImplementedError):
            adapter.fetch_artifact("any")

    def test_is_mock_false(self):
        self.assertFalse(agent.GithubActionsAgent().is_mock)


if __name__ == "__main__":
    unittest.main()
