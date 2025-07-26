from daytona import Sandbox

from ..tools.base import Tool


class SandboxToolBase(Tool):
    """Base class for tools that require a sandbox client."""

    workspace_path = "/trae_agent"

    def __init__(self, model_provider: str | None = None, sandbox: Sandbox = None):
        super().__init__(model_provider)
        self._sandbox = sandbox

    async def wait_for_ready(self):
        await self._sandbox_client.wait_for_ready()
