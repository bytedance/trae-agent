"""命令队列管理器测试用例

测试命令队列的各种功能，包括命令添加、状态管理、持久化存储等。
"""

import asyncio
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from trae_agent.utils.command_queue import (
    CommandQueue,
    CommandStatus,
    QueuedCommand,
    get_command_queue,
)


class TestQueuedCommand(unittest.TestCase):
    """测试QueuedCommand类"""

    def test_queued_command_creation(self):
        """测试命令对象创建"""
        command = QueuedCommand(
            id="test_id",
            task="test task",
            working_dir="/test/dir",
            options={"provider": "openai"}
        )
        
        self.assertEqual(command.id, "test_id")
        self.assertEqual(command.task, "test task")
        self.assertEqual(command.working_dir, "/test/dir")
        self.assertEqual(command.options["provider"], "openai")
        self.assertEqual(command.status, CommandStatus.PENDING)
        self.assertIsNotNone(command.created_at)
        self.assertIsNone(command.started_at)
        self.assertIsNone(command.completed_at)
        self.assertIsNone(command.error_message)

    def test_queued_command_with_custom_time(self):
        """测试使用自定义时间创建命令"""
        custom_time = 1234567890.0
        command = QueuedCommand(
            id="test_id",
            task="test task",
            working_dir="/test/dir",
            options={},
            created_at=custom_time
        )
        
        self.assertEqual(command.created_at, custom_time)


class TestCommandQueue(unittest.TestCase):
    """测试CommandQueue类"""

    def setUp(self):
        """测试前准备"""
        # 创建临时文件用于测试
        self.temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".json")
        self.temp_file.close()
        self.queue_file = self.temp_file.name
        self.queue = CommandQueue(self.queue_file)

    def tearDown(self):
        """测试后清理"""
        # 删除临时文件
        if os.path.exists(self.queue_file):
            os.unlink(self.queue_file)

    def test_add_command(self):
        """测试添加命令"""
        command_id = self.queue.add_command(
            task="test task",
            working_dir="/test/dir",
            options={"provider": "openai"}
        )
        
        self.assertIsNotNone(command_id)
        self.assertTrue(command_id.startswith("cmd_"))
        
        # 验证命令已添加到队列
        commands = self.queue.get_commands()
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].id, command_id)
        self.assertEqual(commands[0].task, "test task")
        self.assertEqual(commands[0].working_dir, "/test/dir")
        self.assertEqual(commands[0].options["provider"], "openai")

    def test_get_queue_status(self):
        """测试获取队列状态"""
        # 初始状态
        status = self.queue.get_queue_status()
        self.assertEqual(status["total"], 0)
        self.assertEqual(status["pending"], 0)
        self.assertEqual(status["running"], 0)
        self.assertEqual(status["completed"], 0)
        self.assertEqual(status["failed"], 0)
        self.assertFalse(status["is_processing"])
        self.assertIsNone(status["current_command"])
        
        # 添加命令后
        self.queue.add_command("task1", "/dir1", {})
        self.queue.add_command("task2", "/dir2", {})
        
        status = self.queue.get_queue_status()
        self.assertEqual(status["total"], 2)
        self.assertEqual(status["pending"], 2)
        self.assertEqual(status["running"], 0)
        self.assertEqual(status["completed"], 0)
        self.assertEqual(status["failed"], 0)

    def test_get_commands_with_filter(self):
        """测试按状态过滤命令"""
        # 添加不同状态的命令
        cmd1_id = self.queue.add_command("task1", "/dir1", {})
        cmd2_id = self.queue.add_command("task2", "/dir2", {})
        
        # 手动修改一个命令的状态
        commands = self.queue.get_commands()
        commands[0].status = CommandStatus.COMPLETED
        
        # 测试过滤
        pending_commands = self.queue.get_commands(CommandStatus.PENDING)
        completed_commands = self.queue.get_commands(CommandStatus.COMPLETED)
        
        self.assertEqual(len(pending_commands), 1)
        self.assertEqual(len(completed_commands), 1)
        self.assertEqual(pending_commands[0].id, cmd2_id)
        self.assertEqual(completed_commands[0].id, cmd1_id)

    def test_cancel_command(self):
        """测试取消命令"""
        # 添加命令
        command_id = self.queue.add_command("test task", "/test/dir", {})
        
        # 取消命令
        result = self.queue.cancel_command(command_id)
        self.assertTrue(result)
        
        # 验证命令状态已更改
        commands = self.queue.get_commands()
        self.assertEqual(commands[0].status, CommandStatus.CANCELLED)
        
        # 尝试取消不存在的命令
        result = self.queue.cancel_command("nonexistent_id")
        self.assertFalse(result)
        
        # 尝试取消已完成的命令
        commands[0].status = CommandStatus.COMPLETED
        result = self.queue.cancel_command(command_id)
        self.assertFalse(result)

    def test_clear_completed(self):
        """测试清除已完成的命令（包括成功完成、失败和已取消的命令）"""
        # 添加命令
        cmd1_id = self.queue.add_command("task1", "/dir1", {})
        cmd2_id = self.queue.add_command("task2", "/dir2", {})
        cmd3_id = self.queue.add_command("task3", "/dir3", {})
        cmd4_id = self.queue.add_command("task4", "/dir4", {})
        
        # 手动设置命令状态
        commands = self.queue.get_commands()
        commands[0].status = CommandStatus.COMPLETED
        commands[1].status = CommandStatus.CANCELLED
        commands[2].status = CommandStatus.FAILED
        # commands[3] 保持 PENDING 状态
        
        # 清除已完成的命令
        cleared_count = self.queue.clear_completed()
        self.assertEqual(cleared_count, 3)
        
        # 验证只剩下待执行的命令
        remaining_commands = self.queue.get_commands()
        self.assertEqual(len(remaining_commands), 1)
        self.assertEqual(remaining_commands[0].id, cmd4_id)
        self.assertEqual(remaining_commands[0].status, CommandStatus.PENDING)

    def test_persistence(self):
        """测试持久化存储"""
        # 添加命令
        command_id = self.queue.add_command(
            task="persistent task",
            working_dir="/persistent/dir",
            options={"provider": "test"}
        )
        
        # 验证文件已创建
        self.assertTrue(os.path.exists(self.queue_file))
        
        # 创建新的队列实例，应该能加载之前的数据
        new_queue = CommandQueue(self.queue_file)
        commands = new_queue.get_commands()
        
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].id, command_id)
        self.assertEqual(commands[0].task, "persistent task")
        self.assertEqual(commands[0].working_dir, "/persistent/dir")
        self.assertEqual(commands[0].options["provider"], "test")
        self.assertEqual(commands[0].status, CommandStatus.PENDING)

    def test_load_queue_with_running_status(self):
        """测试加载队列时重置运行中的命令状态"""
        # 手动创建包含运行中命令的队列文件
        queue_data = [{
            "id": "test_cmd",
            "task": "test task",
            "working_dir": "/test/dir",
            "options": {},
            "status": "running",
            "created_at": time.time(),
            "started_at": time.time()
        }]
        
        with open(self.queue_file, 'w', encoding='utf-8') as f:
            json.dump(queue_data, f)
        
        # 创建新的队列实例
        new_queue = CommandQueue(self.queue_file)
        commands = new_queue.get_commands()
        
        # 验证运行中的命令被重置为待执行状态
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].status, CommandStatus.PENDING)
        self.assertIsNone(commands[0].started_at)

    @patch('trae_agent.utils.command_queue.Console')
    async def test_process_queue(self, mock_console_class):
        """测试队列处理"""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console
        
        # 添加测试命令
        self.queue.add_command("task1", "/dir1", {})
        self.queue.add_command("task2", "/dir2", {})
        
        # 创建模拟执行函数
        executed_commands = []
        
        async def mock_executor(command):
            executed_commands.append(command.id)
            await asyncio.sleep(0.01)  # 模拟执行时间
        
        # 处理队列
        await self.queue.process_queue(mock_executor)
        
        # 验证所有命令都被执行
        self.assertEqual(len(executed_commands), 2)
        
        # 验证命令状态
        commands = self.queue.get_commands()
        for command in commands:
            self.assertEqual(command.status, CommandStatus.COMPLETED)
            self.assertIsNotNone(command.started_at)
            self.assertIsNotNone(command.completed_at)

    @patch('trae_agent.utils.command_queue.Console')
    async def test_process_queue_with_error(self, mock_console_class):
        """测试队列处理时的错误处理"""
        mock_console = MagicMock()
        mock_console_class.return_value = mock_console
        
        # 添加测试命令
        self.queue.add_command("failing task", "/dir1", {})
        
        # 创建会抛出异常的执行函数
        async def failing_executor(command):
            raise Exception("Test error")
        
        # 处理队列
        await self.queue.process_queue(failing_executor)
        
        # 验证命令状态为失败
        commands = self.queue.get_commands()
        self.assertEqual(len(commands), 1)
        self.assertEqual(commands[0].status, CommandStatus.FAILED)
        self.assertEqual(commands[0].error_message, "Test error")
        self.assertIsNotNone(commands[0].started_at)
        self.assertIsNotNone(commands[0].completed_at)


class TestGlobalQueue(unittest.TestCase):
    """测试全局队列功能"""

    def test_get_command_queue_singleton(self):
        """测试全局队列单例模式"""
        queue1 = get_command_queue()
        queue2 = get_command_queue()
        
        # 应该返回同一个实例
        self.assertIs(queue1, queue2)

    def tearDown(self):
        """清理全局队列"""
        # 重置全局队列
        import trae_agent.utils.command_queue
        trae_agent.utils.command_queue._global_queue = None


if __name__ == '__main__':
    unittest.main()