from typing import override

from daytona import Sandbox, SessionExecuteRequest
from daytona_api_client import Session

from ...tools.base import ToolCallArguments, ToolExecResult, ToolParameter
from ..bash_tool import BashTool
from ..sandbox_base import SandboxToolBase


class SandboxBashTool(SandboxToolBase):
    """
    same as BashTool, but run in sandbox
    """

    def __init__(self, model_provider: str | None = None, sandbox: Sandbox | None = None):
        super().__init__(model_provider, sandbox)
        # composition bash tool, do not use multi extend
        self._bash_tool = BashTool(model_provider)
        self._session: Session | None = None

    @override
    def get_name(self) -> str:
        return "sandbox_bash"

    @override
    def get_description(self) -> str:
        return self._bash_tool.get_description()

    @override
    def get_parameters(self) -> list[ToolParameter]:
        return self._bash_tool.get_parameters()

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        session_id = "sd-session"
        if arguments.get("restart"):
            if self._session:
                self._session.process.delete_session(session_id)
            self._sandbox.process.create_session(session_id)
            self._session = self._sandbox.process.get_session(session_id)

            return ToolExecResult(output="tool has been restarted.")

        if self._session is None:
            try:
                self._sandbox.process.create_session(session_id)
                self.session = self._sandbox.process.get_session(session_id)
            except Exception as e:
                return ToolExecResult(error=f"Error starting bash session: {e}", error_code=-1)

        command = str(arguments["command"]) if "command" in arguments else None
        if command is None:
            return ToolExecResult(
                error=f"No command provided for the {self.get_name()} tool",
                error_code=-1,
            )
        try:
            # return await self._session.run(command)
            ret = self._sandbox.process.execute_session_command(
                session_id, SessionExecuteRequest(command=command)
            )
            if ret.exit_code == 0:
                return ToolExecResult(output=ret.output)
            else:
                return ToolExecResult(output=ret.output, error=f"exit_code={ret.exit_code}")
        except Exception as e:
            return ToolExecResult(error=f"Error running bash command: {e}", error_code=-1)
