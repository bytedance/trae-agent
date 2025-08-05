import unittest
from unittest.mock import MagicMock, patch

from asyncclick.testing import CliRunner

from trae_agent.cli import cli


class TestCli(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.runner = CliRunner()

    @patch("trae_agent.cli.Agent")
    @patch("trae_agent.cli.asyncio.run")
    @patch("trae_agent.cli.Config.create")
    @patch("trae_agent.cli.TrajectoryRecorder")
    @patch("trae_agent.cli.ConsoleFactory.create_console")
    async def test_run_with_long_prompt(
        self,
        mock_create_console,
        mock_trajectory_recorder,
        mock_config_create,
        mock_asyncio_run,
        mock_agent_class,
    ):
        """Test that a long prompt string is handled correctly."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.trae_agent = MagicMock()
        mock_config_create.return_value.resolve_config_values.return_value = mock_config
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_console = MagicMock()
        # Add the methods that hasattr checks for
        mock_console.set_initial_task = MagicMock()
        mock_console.set_agent_context = MagicMock()
        mock_create_console.return_value = mock_console

        long_prompt = "a" * 500  # A string longer than typical filename limits
        result = await self.runner.invoke(cli, ["run", long_prompt, "--working-dir", "/tmp"])
        self.assertEqual(result.exit_code, 0)

        # Verify agent.run was called with the long prompt
        mock_asyncio_run.assert_called_once()
        mock_agent.run.assert_called_once()
        args, _ = mock_agent.run.call_args
        self.assertEqual(args[0], long_prompt)

    @patch("trae_agent.cli.Agent")
    @patch("trae_agent.cli.asyncio.run")
    @patch("trae_agent.cli.Config.create")
    @patch("trae_agent.cli.TrajectoryRecorder")
    @patch("trae_agent.cli.ConsoleFactory.create_console")
    async def test_run_with_file_argument(
        self,
        mock_create_console,
        mock_trajectory_recorder,
        mock_config_create,
        mock_asyncio_run,
        mock_agent_class,
    ):
        """Test that the --file argument correctly reads from a file."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.trae_agent = MagicMock()
        mock_config_create.return_value.resolve_config_values.return_value = mock_config
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_console = MagicMock()
        # Add the methods that hasattr checks for
        mock_console.set_initial_task = MagicMock()
        mock_console.set_agent_context = MagicMock()
        mock_create_console.return_value = mock_console

        with self.runner.isolated_filesystem():
            with open("task.txt", "w") as f:
                f.write("task from file")

            result = await self.runner.invoke(
                cli, ["run", "--file", "task.txt", "--working-dir", "/tmp"]
            )
            self.assertEqual(result.exit_code, 0)

            # Verify agent.run was called with the file content
            mock_asyncio_run.assert_called_once()
            mock_agent.run.assert_called_once()
            args, _ = mock_agent.run.call_args
            self.assertEqual(args[0], "task from file")

    async def test_run_with_nonexistent_file(self):
        """Test for a clear error when --file points to a non-existent file."""
        result = await self.runner.invoke(cli, ["run", "--file", "nonexistent.txt"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Error: File not found: nonexistent.txt", result.output)

    async def test_run_with_both_task_and_file(self):
        """Test for a clear error when both task string and --file are used."""
        result = await self.runner.invoke(cli, ["run", "some task", "--file", "task.txt"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn(
            "Error: Cannot use both a task string and the --file argument.", result.output
        )

    async def test_run_with_no_input(self):
        """Test for a clear error when neither task string nor --file is provided."""
        result = await self.runner.invoke(cli, ["run"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn(
            "Error: Must provide either a task string or use the --file argument.", result.output
        )

    @patch("trae_agent.cli.os.chdir", side_effect=FileNotFoundError("No such file or directory"))
    async def test_run_with_nonexistent_working_dir(self, mock_chdir):
        """Test for a clear error when --working-dir points to a non-existent directory."""
        result = await self.runner.invoke(
            cli, ["run", "some task", "--working-dir", "/path/to/nonexistent/dir"]
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Error changing directory", result.output)

    @patch("trae_agent.cli.Agent")
    @patch("trae_agent.cli.asyncio.run")
    @patch("trae_agent.cli.Config.create")
    @patch("trae_agent.cli.TrajectoryRecorder")
    @patch("trae_agent.cli.ConsoleFactory.create_console")
    async def test_run_with_string_that_is_also_a_filename(
        self,
        mock_create_console,
        mock_trajectory_recorder,
        mock_config_create,
        mock_asyncio_run,
        mock_agent_class,
    ):
        """Test that a task string that looks like a file is treated as a string."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.trae_agent = MagicMock()
        mock_config_create.return_value.resolve_config_values.return_value = mock_config
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_console = MagicMock()
        # Add the methods that hasattr checks for
        mock_console.set_initial_task = MagicMock()
        mock_console.set_agent_context = MagicMock()
        mock_create_console.return_value = mock_console

        with self.runner.isolated_filesystem():
            with open("task.txt", "w") as f:
                f.write("file content")

            result = await self.runner.invoke(cli, ["run", "task.txt", "--working-dir", "/tmp"])
            self.assertEqual(result.exit_code, 0)

            # Verify agent.run was called with the string "task.txt", not the file content
            mock_asyncio_run.assert_called_once()
            mock_agent.run.assert_called_once()
            args, _ = mock_agent.run.call_args
            self.assertEqual(args[0], "task.txt")


if __name__ == "__main__":
    unittest.main()
