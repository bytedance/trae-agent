import json
import os
import shlex
from typing import Any

from trae_agent.agent.docker_manager import DockerManager
from trae_agent.tools.base import ToolCall, ToolExecutor, ToolResult


class DockerToolExecutor:
    """
    A ToolExecutor that delegates tool calls to either a local executor
    or a Docker environment based on the tool's name.
    """

    def __init__(
        self,
        original_executor: ToolExecutor,
        docker_manager: DockerManager,
        docker_tools: list[str],
        host_workspace_dir: str | None,
        container_workspace_dir: str,
    ):
        """
        Initializes the DockerToolExecutor.
        """
        self._original_executor = original_executor
        self._docker_manager = docker_manager
        self._docker_tools_set = set(docker_tools)
        # Get path from __init__ ---
        self._host_workspace_dir = (
            os.path.abspath(host_workspace_dir) if host_workspace_dir else None
        )
        self._container_workspace_dir = container_workspace_dir

    def _translate_path(self, host_path: str) -> str:
        """Translate a host path into the corresponding container path.

        Security:
            - Resolves symlinks via ``realpath`` so ``/workspace/foo`` (a symlink
              to ``/etc``) can't be used to escape.
            - Uses ``commonpath`` AND a trailing-separator check to prevent
              prefix collisions like ``/work`` vs ``/workspace``.
            - If the resolved path escapes the host workspace, the path is
              returned unchanged so the downstream Docker command receives
              the literal path (and will likely fail inside the container,
              which is the safe outcome).
        """
        if not self._host_workspace_dir:
            return host_path  # No host workspace → no translation.

        # 1) Resolve to absolute, then to realpath (follows symlinks).
        try:
            abs_host_path = os.path.abspath(host_path)
            real_host_path = os.path.realpath(abs_host_path)
            real_workspace = os.path.realpath(self._host_workspace_dir)
        except (OSError, ValueError):
            # realpath can raise on weird FS states; bail out safely.
            return host_path

        # 2) Confirm the resolved path is under the workspace. Commonpath
        #    alone is insufficient — ``commonpath(['/workspace-evil',
        #    '/workspace'])`` returns ``/workspace`` even though the dirs
        #    are siblings. Append os.sep to both sides before comparing.
        try:
            if os.path.commonpath([real_host_path, real_workspace]) != real_workspace:
                return host_path
        except ValueError:
            # commonpath raises if paths are on different drives (Windows).
            return host_path

        if not (
            real_host_path == real_workspace
            or real_host_path.startswith(real_workspace + os.sep)
        ):
            return host_path

        # 3) Compute the relative path and join into the container dir.
        relative_path = os.path.relpath(real_host_path, real_workspace)
        container_path = os.path.join(self._container_workspace_dir, relative_path)
        return os.path.normpath(container_path)

    async def close_tools(self):
        """
        Closes any resources held by the underlying original executor.
        This method fulfills the contract expected by BaseAgent.
        """
        if self._original_executor:
            return await self._original_executor.close_tools()

    async def sequential_tool_call(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        """Executes tool calls sequentially, routing to Docker if necessary."""
        results = []
        for tool_call in tool_calls:
            if tool_call.name in self._docker_tools_set:
                result = self._execute_in_docker(tool_call)
            else:
                # Execute locally
                result_list = await self._original_executor.sequential_tool_call([tool_call])
                result = result_list[0]
            results.append(result)
        return results

    async def parallel_tool_call(self, tool_calls: list[ToolCall]) -> list[ToolResult]:
        """For simplicity, parallel calls are also executed sequentially."""
        # print(
        #     "[yellow]Warning: Parallel tool calls are executed sequentially in Docker mode.[/yellow]"
        # )
        return await self.sequential_tool_call(tool_calls)

    def _execute_in_docker(self, tool_call: ToolCall) -> ToolResult:
        """
        Builds and executes a command inside the Docker container,
        with path translation.
        """
        try:
            # --- Parameter preprocessing and path translation ---
            processed_args: dict[str, Any] = {}
            for key, value in tool_call.arguments.items():
                # Assuming that all parameters named 'path' are paths that need to be translated
                if key == "path" and isinstance(value, str):
                    translated_path = self._translate_path(value)
                    processed_args[key] = translated_path
                else:
                    processed_args[key] = value

            # --- The subsequent logic now uses' processed'args' instead of 'tool_call. arguments' ---
            command_to_run = ""

            # --- Rule 1: Handling bash tools ---
            if tool_call.name == "bash":
                command_value = processed_args.get("command")
                if not isinstance(command_value, str) or not command_value:
                    raise ValueError("Tool 'bash' requires a non-empty 'command' string argument.")
                command_to_run = command_value

            # --- Rule2 : Handling str_replace_based_edit_tool ---
            elif tool_call.name == "str_replace_based_edit_tool":
                sub_command = processed_args.get("command")
                if not sub_command:
                    raise ValueError("Edit tool called without a 'command' (sub-command).")

                if not isinstance(sub_command, str):
                    raise TypeError(
                        f"The 'command' argument for {tool_call.name} must be a string."
                    )
                executable_path = f"{self._docker_manager.CONTAINER_TOOLS_PATH}/edit_tool"
                cmd_parts = [executable_path, sub_command]

                for key, value in processed_args.items():
                    if key == "command" or value is None:
                        continue
                    if isinstance(value, list):
                        str_value = " ".join(shlex.quote(str(v)) for v in value)
                        cmd_parts.append(f"--{key} {str_value}")
                    else:
                        cmd_parts.append(f"--{key} {shlex.quote(str(value))}")

                command_to_run = " ".join(cmd_parts)
            # --- Rule 3: Handling json_edit_tool ---
            elif tool_call.name == "json_edit_tool":
                executable_path = f"{self._docker_manager.CONTAINER_TOOLS_PATH}/json_edit_tool"
                cmd_parts = [executable_path]
                for key, value in processed_args.items():
                    if value is None:
                        continue
                    # --- Serialize the 'value' parameter into a JSON string ---
                    if key == "value":
                        json_string_value = json.dumps(value)
                        cmd_parts.append(f"--{key} {shlex.quote(json_string_value)}")
                    elif isinstance(value, list):
                        cmd_parts.append(f"--{key} {' '.join(shlex.quote(str(v)) for v in value)}")
                    else:
                        cmd_parts.append(f"--{key} {shlex.quote(str(value))}")
                command_to_run = " ".join(cmd_parts)
            else:
                raise NotImplementedError(
                    f"The logic for Docker execution of tool '{tool_call.name}' is not implemented."
                )

            # Execute the final built command
            exit_code, output = self._docker_manager.execute(command_to_run)
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                result=output,
                success=exit_code == 0,
            )
        except Exception as e:
            return ToolResult(
                call_id=tool_call.call_id,
                name=tool_call.name,
                result=f"Failed to build or execute command for tool '{tool_call.name}' in Docker: {e}",
                success=False,
                error=str(e),
            )
