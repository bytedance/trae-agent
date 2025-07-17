import unittest
from unittest.mock import patch

from click.testing import CliRunner

from trae_agent.cli import cli


class TestCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("trae_agent.cli.create_agent")
    @patch("trae_agent.cli.asyncio.run")
    def test_run_with_long_prompt(self, mock_asyncio_run, mock_create_agent):
        """Test that a long prompt string is handled correctly."""
        long_prompt = "a" * 500  # A string longer than typical filename limits
        result = self.runner.invoke(cli, ["run", long_prompt])
        self.assertEqual(result.exit_code, 0)
        mock_create_agent.return_value.new_task.assert_called_once()
        call_args, _ = mock_create_agent.return_value.new_task.call_args
        self.assertEqual(call_args[0], long_prompt)

    @patch("trae_agent.cli.create_agent")
    @patch("trae_agent.cli.asyncio.run")
    def test_run_with_file_argument(self, mock_asyncio_run, mock_create_agent):
        """Test that the --file argument correctly reads from a file."""
        with self.runner.isolated_filesystem():
            with open("task.txt", "w") as f:
                f.write("task from file")

            result = self.runner.invoke(cli, ["run", "--file", "task.txt"])
            self.assertEqual(result.exit_code, 0)
            mock_create_agent.return_value.new_task.assert_called_once()
            call_args, _ = mock_create_agent.return_value.new_task.call_args
            self.assertEqual(call_args[0], "task from file")

    def test_run_with_nonexistent_file(self):
        """Test for a clear error when --file points to a non-existent file."""
        result = self.runner.invoke(cli, ["run", "--file", "nonexistent.txt"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Error: File not found: nonexistent.txt", result.output)

    def test_run_with_both_task_and_file(self):
        """Test for a clear error when both task string and --file are used."""
        result = self.runner.invoke(cli, ["run", "some task", "--file", "task.txt"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn(
            "Error: Cannot use both a task string and the --file argument.", result.output
        )

    def test_run_with_no_input(self):
        """Test for a clear error when neither task string nor --file is provided."""
        result = self.runner.invoke(cli, ["run"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn(
            "Error: Must provide either a task string or use the --file argument.", result.output
        )

    def test_run_with_nonexistent_working_dir(self):
        """Test for a clear error when --working-dir points to a non-existent directory."""
        result = self.runner.invoke(
            cli, ["run", "some task", "--working-dir", "/path/to/nonexistent/dir"]
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Error changing directory", result.output)

    @patch("trae_agent.cli.create_agent")
    @patch("trae_agent.cli.asyncio.run")
    def test_run_with_string_that_is_also_a_filename(self, mock_asyncio_run, mock_create_agent):
        """Test that a task string that looks like a file is treated as a string."""
        with self.runner.isolated_filesystem():
            with open("task.txt", "w") as f:
                f.write("file content")

            result = self.runner.invoke(cli, ["run", "task.txt"])
            self.assertEqual(result.exit_code, 0)

            mock_create_agent.return_value.new_task.assert_called_once()
            call_args, _ = mock_create_agent.return_value.new_task.call_args
            self.assertEqual(call_args[0], "task.txt")

    @patch("trae_agent.cli.create_agent")
    def test_run_handles_agent_exception(self, mock_create_agent):
        """Test that the CLI handles exceptions raised from the agent gracefully."""
        # deliberately make the mock agent's execute_task raise an error
        mock_agent_instance = mock_create_agent.return_value
        mock_agent_instance.execute_task.side_effect = Exception("Core agent failed")

        result = self.runner.invoke(cli, ["run", "some task"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Unexpected error: Core agent failed", result.output)


if __name__ == "__main__":
    unittest.main()
