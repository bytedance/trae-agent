import unittest

from trae_agent.tools.base import ToolCallArguments
from trae_agent.tools.bash_tool import BashTool


class TestBashTool(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tool = BashTool()

    async def asyncTearDown(self):
        # Cleanup any active session
        if self.tool._session:
            self.tool._session.stop()

    async def test_tool_initialization(self):
        self.assertEqual(self.tool.get_name(), "bash")
        self.assertIn("Run commands in a bash shell", self.tool.get_description())

        params = self.tool.get_parameters()
        param_names = [p.name for p in params]
        self.assertIn("command", param_names)
        self.assertIn("restart", param_names)

    async def test_command_error_handling(self):
        result = await self.tool.execute(
            ToolCallArguments({"command": "invalid_command_123"})
        )

        # 修复断言：检查错误信息是否包含'not found'或'not recognized'（Windows系统）
        self.assertTrue(
            any(s in result.error.lower() for s in ["not found", "not recognized"])
        )

    async def test_session_restart(self):
        # 确保会话已初始化
        await self.tool.execute(ToolCallArguments({"command": "echo first session"}))

        # 修复：检查会话对象是否存在
        self.assertIsNotNone(self.tool._session)

        # Restart and test new session
        restart_result = await self.tool.execute(ToolCallArguments({"restart": True}))
        self.assertIn("restarted", restart_result.output.lower())

        # 修复：确保新会话已创建
        self.assertIsNotNone(self.tool._session)

        # Verify new session works
        result = await self.tool.execute(
            ToolCallArguments({"command": "echo new session"})
        )
        self.assertIn("new session", result.output)

    async def test_successful_command_execution(self):
        result = await self.tool.execute(
            ToolCallArguments({"command": "echo hello world"})
        )

        # 修复：检查返回码是否为0
        self.assertEqual(result.error_code, 0)
        self.assertIn("hello world", result.output)
        self.assertEqual(result.error, "")

    async def test_missing_command_handling(self):
        result = await self.tool.execute(ToolCallArguments({}))
        self.assertIn("no command provided", result.error.lower())
        self.assertEqual(result.error_code, -1)


if __name__ == "__main__":
    unittest.main()
