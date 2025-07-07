import os
import sys
import unittest
from unittest.mock import MagicMock, patch


sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../")))


from trae_agent.agent.agent_basics import AgentError
from trae_agent.agent.trae_agent import TraeAgent
from trae_agent.utils.config import Config



class TestTraeAgentExtended(unittest.TestCase):
    def setUp(self):
        self.config = Config({"llm": {"provider": "test", "model": "test-model"}})
        self.agent = TraeAgent(self.config)
        self.test_project_path = "/test/project"
        self.test_patch_path = "/test/patch.diff"

    @patch("trae_agent.utils.trajectory_recorder.TrajectoryRecorder")
    def test_trajectory_setup(self, mock_recorder):
        _ = self.agent.setup_trajectory_recording()
        self.assertIsNotNone(self.agent.trajectory_recorder)
        mock_recorder.return_value.start_recording.assert_called_once()

    def test_new_task_initialization(self):
        with self.assertRaises(AgentError):
            self.agent.new_task("test", {})  # Missing required params

        valid_args = {
            "project_path": self.test_project_path,
            "issue": "Test issue",
            "base_commit": "abc123",
            "must_patch": "true",
            "patch_path": self.test_patch_path,
        }
        self.agent.new_task("test-task", valid_args)

        self.assertEqual(self.agent.project_path, self.test_project_path)
        self.assertEqual(self.agent.must_patch, "true")
        self.assertEqual(len(self.agent.tools), 4)
        self.assertTrue(any(tool.get_name() == "bash" for tool in self.agent.tools))

    @patch("subprocess.check_output")
    def test_git_diff_generation(self, mock_subprocess):
        mock_subprocess.return_value = b"test diff"
        self.agent.project_path = self.test_project_path

        diff = self.agent.get_git_diff()
        self.assertEqual(diff, "test diff")
        mock_subprocess.assert_called_with(["git", "--no-pager", "diff"])

    def test_patch_filtering(self):
        test_patch = """diff --git a/tests/test_example.py b/tests/test_example.py
--- a/tests/test_example.py
+++ b/tests/test_example.py
@@ -5,6 +5,7 @@
     def test_example(self):
         assert True
"""
        filtered = self.agent.remove_patches_to_tests(test_patch)
        self.assertEqual(filtered, "")

    @patch("asyncio.create_task")
    @patch("trae_agent.utils.cli_console.CliConsole")
    def test_task_execution_flow(self, mock_console, mock_task):
        self.agent.cli_console = mock_console
        _ = self.agent.execute_task()
        mock_console.start.assert_called_once()

    def test_task_completion_detection(self):
        # Test empty patch scenario
        self.agent.must_patch = "true"
        self.assertFalse(self.agent.is_task_completed(MagicMock()))

        # Test valid patch scenario
        with patch.object(self.agent, "get_git_diff", return_value="valid patch"):
            self.assertTrue(self.agent.is_task_completed(MagicMock()))

    def test_tool_initialization(self):
        tools = [
            "bash",
            "str_replace_based_edit_tool",
            "sequentialthinking",
            "task_done",
        ]
        self.agent.new_task(
            "test", {"project_path": self.test_project_path, "tool_names": tools}
        )
        self.assertEqual(len(self.agent.tools), len(tools))
        self.assertEqual(self.agent.tools[0].get_name(), "bash")


if __name__ == "__main__":
    unittest.main()
