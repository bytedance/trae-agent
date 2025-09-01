"""命令队列管理器模块

提供命令缓存、持久化存储和顺序执行功能，确保命令不会丢失且按正确顺序执行。
"""

import asyncio
import json
import threading
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import os
import platform

from rich.console import Console

# 根据操作系统选择文件锁实现
if platform.system() == 'Windows':
    import msvcrt
else:
    import fcntl


class CommandStatus(Enum):
    """命令状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueuedCommand:
    """队列中的命令对象
    
    Args:
        id: 命令唯一标识符
        task: 任务描述
        working_dir: 工作目录
        options: 命令选项参数
        status: 命令状态
        created_at: 创建时间戳
        started_at: 开始执行时间戳
        completed_at: 完成时间戳
        error_message: 错误信息
    """
    id: str
    task: str
    working_dir: str
    options: Dict[str, Any]
    status: CommandStatus = CommandStatus.PENDING
    created_at: float = 0.0
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error_message: Optional[str] = None

    def __post_init__(self):
        if self.created_at == 0.0:
            self.created_at = time.time()


def _lock_file(file_handle):
    """跨平台文件锁定
    
    Args:
        file_handle: 文件句柄
    """
    if platform.system() == 'Windows':
        # Windows使用msvcrt
        while True:
            try:
                msvcrt.locking(file_handle.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except IOError:
                time.sleep(0.01)
    else:
        # Unix/Linux使用fcntl
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_EX)


def _unlock_file(file_handle):
    """跨平台文件解锁
    
    Args:
        file_handle: 文件句柄
    """
    if platform.system() == 'Windows':
        # Windows使用msvcrt
        try:
            msvcrt.locking(file_handle.fileno(), msvcrt.LK_UNLCK, 1)
        except IOError:
            pass
    else:
        # Unix/Linux使用fcntl
        fcntl.flock(file_handle.fileno(), fcntl.LOCK_UN)


class CommandQueue:
    """命令队列管理器
    
    提供线程安全的命令队列管理，支持持久化存储和异步执行。
    """

    def __init__(self, queue_file: Optional[str] = None):
        """初始化命令队列管理器
        
        Args:
            queue_file: 队列持久化文件路径，默认为用户目录下的.trae_queue.json
        """
        self._queue: List[QueuedCommand] = []
        self._lock = threading.RLock()
        self._running = False
        self._current_command: Optional[QueuedCommand] = None
        self._console = Console()
        
        # 设置队列文件路径
        if queue_file:
            self._queue_file = Path(queue_file)
        else:
            self._queue_file = Path.home() / ".trae_queue.json"
        
        # 加载已存在的队列
        self._load_queue()

    def add_command(self, task: str, working_dir: str, options: Dict[str, Any]) -> str:
        """添加命令到队列
        
        Args:
            task: 任务描述
            working_dir: 工作目录
            options: 命令选项参数
            
        Returns:
            命令ID
        """
        with self._lock:
            command_id = f"cmd_{int(time.time() * 1000)}_{len(self._queue)}"
            command = QueuedCommand(
                id=command_id,
                task=task,
                working_dir=working_dir,
                options=options
            )
            self._queue.append(command)
            self._save_queue()
            return command_id

    def get_queue_status(self) -> Dict[str, Any]:
        """获取队列状态信息
        
        Returns:
            包含队列状态的字典
        """
        with self._lock:
            pending_count = sum(1 for cmd in self._queue if cmd.status == CommandStatus.PENDING)
            running_count = sum(1 for cmd in self._queue if cmd.status == CommandStatus.RUNNING)
            completed_count = sum(1 for cmd in self._queue if cmd.status == CommandStatus.COMPLETED)
            failed_count = sum(1 for cmd in self._queue if cmd.status == CommandStatus.FAILED)
            
            return {
                "total": len(self._queue),
                "pending": pending_count,
                "running": running_count,
                "completed": completed_count,
                "failed": failed_count,
                "is_processing": self._is_processor_running(),
                "current_command": self._current_command.id if self._current_command else None
            }

    def get_commands(self, status: Optional[CommandStatus] = None) -> List[QueuedCommand]:
        """获取命令列表
        
        Args:
            status: 过滤特定状态的命令，None表示获取所有命令
            
        Returns:
            命令列表
        """
        with self._lock:
            if status is None:
                return self._queue.copy()
            return [cmd for cmd in self._queue if cmd.status == status]

    def cancel_command(self, command_id: str) -> bool:
        """取消指定命令
        
        Args:
            command_id: 命令ID
            
        Returns:
            是否成功取消
        """
        with self._lock:
            for command in self._queue:
                if command.id == command_id and command.status == CommandStatus.PENDING:
                    command.status = CommandStatus.CANCELLED
                    self._save_queue()
                    return True
            return False

    def clear_completed(self) -> int:
        """清除已完成的命令（包括成功完成、失败和已取消的命令）
        
        Returns:
            清除的命令数量
        """
        with self._lock:
            original_count = len(self._queue)
            self._queue = [cmd for cmd in self._queue 
                          if cmd.status not in [CommandStatus.COMPLETED, CommandStatus.CANCELLED, CommandStatus.FAILED]]
            cleared_count = original_count - len(self._queue)
            if cleared_count > 0:
                self._save_queue()
            return cleared_count

    async def process_queue(self, executor_func):
        """处理队列中的命令
        
        Args:
            executor_func: 异步执行函数，接收QueuedCommand参数
        """
        if self._running:
            self._console.print("[yellow]队列处理器已在运行中[/yellow]")
            return

        self._running = True
        
        # 创建进程锁文件
        lock_file = self._queue_file.parent / ".trae_queue.lock"
        try:
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            with open(lock_file, 'w') as f:
                import os
                f.write(str(os.getpid()))
        except Exception as e:
            self._console.print(f"[yellow]创建进程锁文件失败: {e}[/yellow]")
        
        try:
            # 只处理当前队列中的待执行命令，不进入无限循环
            while True:
                # 重新加载队列以获取其他进程添加的新命令
                self._load_queue()
                
                # 获取下一个待执行的命令
                next_command = None
                with self._lock:
                    for command in self._queue:
                        if command.status == CommandStatus.PENDING:
                            next_command = command
                            command.status = CommandStatus.RUNNING
                            command.started_at = time.time()
                            self._current_command = command
                            self._save_queue()
                            break

                if next_command is None:
                    # 没有待执行的命令，退出循环
                    self._console.print("[cyan]队列中没有待执行的命令，处理器退出[/cyan]")
                    break

                self._console.print(f"[blue]开始执行命令: {next_command.task}[/blue]")
                
                try:
                    # 执行命令（这里会应用max_steps限制）
                    await executor_func(next_command)
                    
                    # 标记为完成
                    with self._lock:
                        next_command.status = CommandStatus.COMPLETED
                        next_command.completed_at = time.time()
                        self._current_command = None
                        self._save_queue()
                    
                    self._console.print(f"[green]命令执行完成: {next_command.task}[/green]")
                    
                except Exception as e:
                    # 标记为失败
                    with self._lock:
                        next_command.status = CommandStatus.FAILED
                        next_command.error_message = str(e)
                        next_command.completed_at = time.time()
                        self._current_command = None
                        self._save_queue()
                    
                    self._console.print(f"[red]命令执行失败: {next_command.task} - {e}[/red]")
                
                # 处理完一个命令后，检查是否还有待执行的命令
                # 如果没有，则退出循环，避免无限重复执行

        finally:
            with self._lock:
                self._running = False
                self._current_command = None
                # 在退出前最后一次保存队列状态
                self._save_queue()
            
            # 清理进程锁文件
            try:
                if lock_file.exists():
                    lock_file.unlink()
            except Exception as e:
                self._console.print(f"[yellow]清理进程锁文件失败: {e}[/yellow]")

    def _load_queue(self):
        """从文件加载队列
        
        使用文件锁确保多进程安全访问
        """
        if not self._queue_file.exists():
            return
        
        try:
            with open(self._queue_file, 'r', encoding='utf-8') as f:
                _lock_file(f)
                try:
                    data = json.load(f)
                finally:
                    _unlock_file(f)
            
            # 创建文件中命令的字典，用于合并
            file_commands = {}
            for item in data:
                # 转换状态枚举
                status = CommandStatus(item['status'])
                
                # 如果检测到运行中的命令但没有其他进程在处理队列，将其重置为待执行
                if status == CommandStatus.RUNNING and not self._is_processor_running():
                    status = CommandStatus.PENDING
                
                command = QueuedCommand(
                    id=item['id'],
                    task=item['task'],
                    working_dir=item.get('working_dir', ''),
                    options=item.get('options', {}),
                    status=status,
                    created_at=item['created_at'],
                    started_at=item.get('started_at'),
                    completed_at=item.get('completed_at'),
                    error_message=item.get('error_message')
                )
                file_commands[command.id] = command
            
            # 合并队列：更新现有命令，添加新命令
            existing_ids = {cmd.id for cmd in self._queue}
            
            # 更新现有命令的状态
            for i, cmd in enumerate(self._queue):
                if cmd.id in file_commands:
                    file_cmd = file_commands[cmd.id]
                    # 只更新状态相关字段，保持其他字段不变
                    if cmd.status != file_cmd.status:
                        self._queue[i] = file_cmd
            
            # 添加新命令
            for cmd_id, cmd in file_commands.items():
                if cmd_id not in existing_ids:
                    self._queue.append(cmd)
                
        except Exception as e:
            self._console.print(f"[red]加载队列失败: {e}[/red]")
    
    def _is_processor_running(self) -> bool:
        """检查是否有其他进程正在处理队列
        
        Returns:
            bool: 如果有进程正在处理队列返回True，否则返回False
        """
        try:
            # 检查进程锁文件
            lock_file = self._queue_file.parent / ".trae_queue.lock"
            if lock_file.exists():
                # 读取锁文件中的进程ID
                with open(lock_file, 'r') as f:
                    pid = int(f.read().strip())
                
                # 检查进程是否还在运行
                try:
                    import psutil
                    return psutil.pid_exists(pid)
                except ImportError:
                    # 如果没有psutil，使用简单的时间检查
                    # 如果锁文件存在且修改时间在5分钟内，认为进程还在运行
                    import time
                    lock_time = lock_file.stat().st_mtime
                    return time.time() - lock_time < 300  # 5分钟
            
            return False
        except Exception:
            return False

    def _save_queue(self):
        """保存队列到文件
        
        使用文件锁确保多进程安全访问，保存前先合并其他进程的更新
        """
        try:
            # 确保目录存在
            self._queue_file.parent.mkdir(parents=True, exist_ok=True)
            
            # 在保存前先加载文件中的最新数据进行合并
            if self._queue_file.exists():
                try:
                    with open(self._queue_file, 'r', encoding='utf-8') as f:
                        _lock_file(f)
                        try:
                            file_data = json.load(f)
                        finally:
                            _unlock_file(f)
                    
                    # 创建文件中命令的字典
                    file_commands = {}
                    for item in file_data:
                        status = CommandStatus(item['status'])
                        command = QueuedCommand(
                            id=item['id'],
                            task=item['task'],
                            working_dir=item.get('working_dir', ''),
                            options=item.get('options', {}),
                            status=status,
                            created_at=item['created_at'],
                            started_at=item.get('started_at'),
                            completed_at=item.get('completed_at'),
                            error_message=item.get('error_message')
                        )
                        file_commands[command.id] = command
                    
                    # 合并队列：保留文件中的命令，更新内存中的命令状态
                    memory_commands = {cmd.id: cmd for cmd in self._queue}
                    
                    # 创建合并后的队列 - 保持原有顺序，只添加新命令
                    existing_ids = {cmd.id for cmd in self._queue}
                    
                    # 更新现有命令的状态
                    for i, cmd in enumerate(self._queue):
                        if cmd.id in file_commands:
                            file_cmd = file_commands[cmd.id]
                            # 只有当文件中的命令状态更新时才替换
                            if (file_cmd.completed_at and not cmd.completed_at) or \
                               (file_cmd.status != cmd.status and cmd.status == CommandStatus.RUNNING):
                                self._queue[i] = file_cmd
                    
                    # 添加文件中存在但内存中不存在的新命令
                    for cmd_id, cmd in file_commands.items():
                        if cmd_id not in existing_ids:
                            self._queue.append(cmd)
                    
                except (json.JSONDecodeError, KeyError, ValueError):
                    # 如果文件损坏，使用内存中的数据
                    pass
            
            # 转换为可序列化的格式
            data = []
            for command in self._queue:
                item = asdict(command)
                item['status'] = command.status.value
                data.append(item)
            
            # 使用文件锁写入文件
            with open(self._queue_file, 'w', encoding='utf-8') as f:
                _lock_file(f)
                try:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                finally:
                    _unlock_file(f)
        except Exception as e:
            self._console.print(f"[red]保存队列失败: {e}[/red]")


# 全局队列实例
_global_queue: Optional[CommandQueue] = None


def get_command_queue() -> CommandQueue:
    """获取全局命令队列实例
    
    Returns:
        CommandQueue实例
    """
    global _global_queue
    if _global_queue is None:
        _global_queue = CommandQueue()
    return _global_queue