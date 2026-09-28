import unittest
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from trae_agent.cli import cli


class TestCli(unittest.TestCase):
    def setUp(self):
        self.runner = CliRunner()

    def _resolved_max_steps(self, command_args):
        with self.runner.isolated_filesystem():
            with open("test_config.yaml", "w") as config_file:
                config_file.write(
                    """agents:
  trae_agent:
    enable_lakeview: false
    model: trae_agent_model
    max_steps: 50
    tools: []
model_providers:
  openai:
    provider: openai
    api_key: placeholder
models:
  trae_agent_model:
    model_provider: openai
    model: gpt-4o
    max_tokens: 128
    temperature: 0.0
    top_p: 1
    top_k: 0
    max_retries: 1
    parallel_tool_calls: true
"""
                )

            with (
                patch("trae_agent.cli.Agent") as mock_agent,
                patch("trae_agent.cli.asyncio.run") as mock_asyncio_run,
                patch("trae_agent.cli.ConsoleFactory.create_console", return_value=MagicMock()),
            ):
                result = self.runner.invoke(
                    cli, [*command_args, "--config-file", "test_config.yaml"]
                )
                if command_args[0] == "interactive" and mock_asyncio_run.called:
                    mock_asyncio_run.call_args.args[0].close()

            self.assertEqual(result.exit_code, 0, result.output)
            return mock_agent.call_args.args[1].trae_agent.max_steps

    def test_interactive_uses_configured_max_steps_when_option_is_omitted(self):
        resolved_max_steps = self._resolved_max_steps(["interactive"])

        self.assertEqual(resolved_max_steps, 50)
        self.assertIsInstance(resolved_max_steps, int)
        max_steps_option = next(
            option for option in cli.commands["interactive"].params if option.name == "max_steps"
        )
        self.assertIsNone(max_steps_option.default)

    def test_interactive_cli_max_steps_overrides_config(self):
        self.assertEqual(self._resolved_max_steps(["interactive", "--max-steps", "70"]), 70)

    def test_run_uses_configured_max_steps(self):
        self.assertEqual(self._resolved_max_steps(["run", "test task"]), 50)

    @patch("trae_agent.cli.resolve_config_file", return_value="test_config.yaml")
    @patch("trae_agent.cli.Agent")
    @patch("trae_agent.cli.asyncio.run")
    @patch("trae_agent.cli.Config.create")
    @patch("trae_agent.cli.ConsoleFactory.create_console")
    def test_run_with_long_prompt(
        self,
        mock_create_console,
        mock_config_create,
        mock_asyncio_run,
        mock_agent_class,
        mock_resolve_config_file,
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
        result = self.runner.invoke(cli, ["run", long_prompt, "--working-dir", "/tmp"])
        self.assertEqual(result.exit_code, 0)

        # Verify agent.run was called with the long prompt
        mock_asyncio_run.assert_called_once()
        mock_agent.run.assert_called_once()
        args, _ = mock_agent.run.call_args
        self.assertEqual(args[0], long_prompt)

    @patch("trae_agent.cli.resolve_config_file", return_value="test_config.yaml")
    @patch("trae_agent.cli.Agent")
    @patch("trae_agent.cli.asyncio.run")
    @patch("trae_agent.cli.Config.create")
    @patch("trae_agent.cli.ConsoleFactory.create_console")
    def test_run_with_file_argument(
        self,
        mock_create_console,
        mock_config_create,
        mock_asyncio_run,
        mock_agent_class,
        mock_resolve_config_file,
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

            result = self.runner.invoke(cli, ["run", "--file", "task.txt", "--working-dir", "/tmp"])
            self.assertEqual(result.exit_code, 0)

            # Verify agent.run was called with the file content
            mock_asyncio_run.assert_called_once()
            mock_agent.run.assert_called_once()
            args, _ = mock_agent.run.call_args
            self.assertEqual(args[0], "task from file")

    @patch("trae_agent.cli.resolve_config_file", return_value="test_config.yaml")
    def test_run_with_nonexistent_file(self, mock_resolve_config_file):
        """Test for a clear error when --file points to a non-existent file."""
        result = self.runner.invoke(cli, ["run", "--file", "nonexistent.txt"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Error: File not found: nonexistent.txt", result.output)

    @patch("trae_agent.cli.resolve_config_file", return_value="test_config.yaml")
    def test_run_with_both_task_and_file(self, mock_resolve_config_file):
        """Test for a clear error when both task string and --file are used."""
        result = self.runner.invoke(cli, ["run", "some task", "--file", "task.txt"])
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn(
            "Error: Cannot use both a task string and the --file argument.", result.output
        )

    def test_run_with_no_input(self):
        """Test for a clear error when neither task string nor --file is provided."""
        result = self.runner.invoke(cli, ["run"])
        self.assertIn("Error: Config file not found.", result.output)

    @patch("trae_agent.cli.resolve_config_file", return_value="test_config.yaml")
    @patch("trae_agent.cli.Agent")
    @patch("trae_agent.cli.Config.create")
    @patch("trae_agent.cli.ConsoleFactory.create_console")
    @patch("trae_agent.cli.os.chdir", side_effect=FileNotFoundError("No such file or directory"))
    def test_run_with_nonexistent_working_dir(
        self,
        mock_chdir,
        mock_create_console,
        mock_config_create,
        mock_agent_class,
        mock_resolve_config_file,
    ):
        """Test for a clear error when --working-dir points to a non-existent directory."""
        # Setup mocks
        mock_config = MagicMock()
        mock_config.trae_agent = MagicMock()
        mock_config_create.return_value.resolve_config_values.return_value = mock_config
        mock_agent = MagicMock()
        mock_agent_class.return_value = mock_agent
        mock_console = MagicMock()
        mock_console.set_initial_task = MagicMock()
        mock_console.set_agent_context = MagicMock()
        mock_create_console.return_value = mock_console

        result = self.runner.invoke(
            cli, ["run", "some task", "--working-dir", "/path/to/nonexistent/dir"]
        )
        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("Error changing directory", result.output)

    @patch("trae_agent.cli.resolve_config_file", return_value="test_config.yaml")
    @patch("trae_agent.cli.Agent")
    @patch("trae_agent.cli.asyncio.run")
    @patch("trae_agent.cli.Config.create")
    @patch("trae_agent.cli.ConsoleFactory.create_console")
    def test_run_with_string_that_is_also_a_filename(
        self,
        mock_create_console,
        mock_config_create,
        mock_asyncio_run,
        mock_agent_class,
        mock_resolve_config_file,
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

            result = self.runner.invoke(cli, ["run", "task.txt", "--working-dir", "/tmp"])
            self.assertEqual(result.exit_code, 0)

            # Verify agent.run was called with the string "task.txt", not the file content
            mock_asyncio_run.assert_called_once()
            mock_agent.run.assert_called_once()
            args, _ = mock_agent.run.call_args
            self.assertEqual(args[0], "task.txt")


if __name__ == "__main__":
    unittest.main()
