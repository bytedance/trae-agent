"""Command Queue Manager Module

Provides command caching, persistent storage, and sequential execution functionality,
ensuring commands are not lost and executed in the correct order.
"""

import asyncio
import json
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import os

from rich.console import Console

class CommandStatus(Enum):
    """Command status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class QueuedCommand:
    """Queued command object
    
    Args:
        id: Command unique identifier
        task: Task description
        working_dir: Working directory
        options: Command option parameters
        status: Command status
        created_at: Creation timestamp
        started_at: Start execution timestamp
        completed_at: Completion timestamp
        error_message: Error message
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





class CommandQueue:
    """Command queue manager
    Provides thread-safe command queue management with persistent storage and asynchronous execution.
    """

    def __init__(self, queue_file: Optional[str] = None):
        """Initialize command queue manager  
        Args:
            queue_file: Queue persistence file path, defaults to .trae_queue.json in user directory
        """
        self._queue: List[QueuedCommand] = []
        self._running = False
        self._current_command: Optional[QueuedCommand] = None
        self._console = Console()
        
        # Set queue file path
        if queue_file:
            self._queue_file = Path(queue_file)
        else:
            # Use trae_queue.json file in project root directory
            self._queue_file = Path.cwd() / "trae_queue.json"
        
        # Load existing queue
        self._load_queue()

    def add_command(self, task: str, working_dir: str, options: Dict[str, Any]) -> str:
        """Add command to queue
        Args:
            task: Task description
            working_dir: Working directory
            options: Command option parameters
        Returns:
            Command ID
        """
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
        """Get queue status information
        Returns:
            Dictionary containing queue status
        """
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
        """Get command list
        Args:
            status: Filter commands with specific status, None means get all commands
        Returns:
            Command list
        """
        if status is None:
            return self._queue.copy()
        return [cmd for cmd in self._queue if cmd.status == status]

    def cancel_command(self, command_id: str) -> bool:
        """Cancel specified command
        Args:
            command_id: Command ID
        Returns:
            Whether successfully cancelled
        """
        for command in self._queue:
            if command.id == command_id and command.status == CommandStatus.PENDING:
                command.status = CommandStatus.CANCELLED
                self._save_queue()
                return True
        return False

    def cancel_all(self) -> int:
        """Cancel all pending commands
        Returns:
            Number of cancelled commands
        """
        cancelled_count = 0
        for command in self._queue:
            if command.status == CommandStatus.PENDING:
                command.status = CommandStatus.CANCELLED
                cancelled_count += 1
        
        if cancelled_count > 0:
            self._save_queue()
        return cancelled_count

    def clear_completed(self) -> int:
        """Clear completed commands (including successfully completed, failed, and cancelled commands)
        Returns:
            Number of cleared commands
        """
        original_count = len(self._queue)
        self._queue = [cmd for cmd in self._queue 
                      if cmd.status not in [CommandStatus.COMPLETED, CommandStatus.CANCELLED, CommandStatus.FAILED]]
        cleared_count = original_count - len(self._queue)
        if cleared_count > 0:
            self._save_queue(merge_file_data=False)
        return cleared_count

    async def process_queue(self, executor_func):
        """Process commands in the queue
        Args:
            executor_func: Asynchronous execution function that accepts QueuedCommand parameter
        """
        if self._running:
            self._console.print("[yellow]Queue processor is already running[/yellow]")
            return

        self._running = True
        
        # Create process lock file
        lock_file = self._queue_file.parent / ".trae_queue.lock"
        try:
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            with open(lock_file, 'w') as f:
                import os
                f.write(str(os.getpid()))
        except Exception as e:
            self._console.print(f"[yellow]Failed to create process lock file: {e}[/yellow]")
        
        try:
            # Only process pending commands in current queue, don't enter infinite loop
            while True:
                # Reload queue to get new commands added by other processes
                self._load_queue()
                
                # Get next pending command
                next_command = None
                for command in self._queue:
                    if command.status == CommandStatus.PENDING:
                        next_command = command
                        command.status = CommandStatus.RUNNING
                        command.started_at = time.time()
                        self._current_command = command
                        self._save_queue()
                        break

                if next_command is None:
                    # No pending commands, exit loop
                    self._console.print("[cyan]No pending commands in queue, processor exiting[/cyan]")
                    break

                self._console.print(f"[blue]Starting command execution: {next_command.task}[/blue]")
                
                try:
                    # Execute command (max_steps limit will be applied here)
                    await executor_func(next_command)
                    
                    # Mark as completed
                    next_command.status = CommandStatus.COMPLETED
                    next_command.completed_at = time.time()
                    self._current_command = None
                    self._save_queue()
                    
                    self._console.print(f"[green]Command execution completed: {next_command.task}[/green]")
                    
                except Exception as e:
                    # Mark as failed
                    next_command.status = CommandStatus.FAILED
                    next_command.error_message = str(e)
                    next_command.completed_at = time.time()
                    self._current_command = None
                    self._save_queue()
                    
                    self._console.print(f"[red]Command execution failed: {next_command.task} - {e}[/red]")
                
                # After processing one command, check if there are more pending commands
                # If not, exit loop to avoid infinite repetition

        finally:
            self._running = False
            self._current_command = None
            # Save queue state one last time before exiting
            self._save_queue()
            
            # Clean up process lock file
            try:
                if lock_file.exists():
                    lock_file.unlink()
            except Exception as e:
                self._console.print(f"[yellow]Failed to clean up process lock file: {e}[/yellow]")

    def _load_queue(self):
        """Load queue from file
        """
        if not self._queue_file.exists():
            return
        
        try:
            with open(self._queue_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Create dictionary of commands from file for merging
            file_commands = {}
            for item in data:
                # Convert status enum
                status = CommandStatus(item['status'])
                
                # Only reset running commands when current process is not the processor
                # Avoid incorrectly resetting commands being executed in the same processor process
                started_at = item.get('started_at')
                if status == CommandStatus.RUNNING and not self._running and not self._is_processor_running():
                    status = CommandStatus.PENDING
                    started_at = None
                
                command = QueuedCommand(
                    id=item['id'],
                    task=item['task'],
                    working_dir=item.get('working_dir', ''),
                    options=item.get('options', {}),
                    status=status,
                    created_at=item['created_at'],
                    started_at=started_at,
                    completed_at=item.get('completed_at'),
                    error_message=item.get('error_message')
                )
                file_commands[command.id] = command
            
            # Merge queue: update existing commands, add new commands
            existing_ids = {cmd.id for cmd in self._queue}
            
            # Update status of existing commands
            for i, cmd in enumerate(self._queue):
                if cmd.id in file_commands:
                    file_cmd = file_commands[cmd.id]
                    # Only update status-related fields, keep other fields unchanged
                    if cmd.status != file_cmd.status:
                        self._queue[i] = file_cmd
            
            # Add new commands
            for cmd_id, cmd in file_commands.items():
                if cmd_id not in existing_ids:
                    self._queue.append(cmd)
                
        except Exception as e:
            self._console.print(f"[red]Failed to load queue: {e}[/red]")
    
    def _is_processor_running(self) -> bool:
        """Check if another process is processing the queue
        
        Returns:
            bool: Returns True if a process is processing the queue, otherwise False
        """
        try:
            # Check process lock file
            lock_file = self._queue_file.parent / ".trae_queue.lock"
            if lock_file.exists():
                # Read process ID from lock file
                with open(lock_file, 'r') as f:
                    pid = int(f.read().strip())
                
                # Check if process is still running
                try:
                    import psutil
                    return psutil.pid_exists(pid)
                except ImportError:
                    import time
                    lock_time = lock_file.stat().st_mtime
                    return time.time() - lock_time < 300  # 5 minutes
            
            return False
        except Exception:
            return False

    def _save_queue(self, merge_file_data=True):
        """Save queue to file
        
        Args:
            merge_file_data: Whether to merge data from file before saving, defaults to True
        """
        try:
            # Ensure directory exists
            self._queue_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Load latest data from file for merging before saving (if needed)
            if merge_file_data and self._queue_file.exists():
                try:
                    with open(self._queue_file, 'r', encoding='utf-8') as f:
                        file_data = json.load(f)
                    
                    # Create dictionary of commands from file
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
                    
                    # Merge queue: keep commands from file, update status of commands in memory
                    memory_commands = {cmd.id: cmd for cmd in self._queue}
                    
                    # Create merged queue - maintain original order, only add new commands
                    existing_ids = {cmd.id for cmd in self._queue}
                    
                    # Update status of existing commands
                    for i, cmd in enumerate(self._queue):
                        if cmd.id in file_commands:
                            file_cmd = file_commands[cmd.id]
                            # Use latest status from memory, as memory status is most up-to-date
                            # Don't overwrite updated status in memory with status from file
                            pass  # Keep status in memory
                    
                    # Add new commands that exist in file but not in memory
                    for cmd_id, cmd in file_commands.items():
                        if cmd_id not in existing_ids:
                            self._queue.append(cmd)
                    
                except (json.JSONDecodeError, KeyError, ValueError):
                    # If file is corrupted, use data from memory
                    pass
            
            # Convert to serializable format
            data = []
            for command in self._queue:
                item = asdict(command)
                item['status'] = command.status.value
                data.append(item)
            
            # Write to file
            with open(self._queue_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            self._console.print(f"[red]Failed to save queue: {e}[/red]")


# Global queue instance
_global_queue: Optional[CommandQueue] = None


def get_command_queue() -> CommandQueue:
    """Get global command queue instance
    
    Returns:
        CommandQueue instance
    """
    global _global_queue
    if _global_queue is None:
        _global_queue = CommandQueue()
    return _global_queue