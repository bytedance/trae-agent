"""Temporary working directory management for agent execution."""

import os
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncGenerator, Optional

from trae_api.core.settings import get_settings


class TempDirManager:
    """Manages temporary working directories for agent execution."""
    
    def __init__(self, base_temp_dir: Optional[Path] = None):
        """
        Initialize TempDirManager.
        
        Args:
            base_temp_dir: Base directory for temporary folders. 
                          Defaults to data/temp/ from trae_api settings.
        """
        if base_temp_dir is None:
            settings = get_settings()
            self.base_temp_dir = settings.data_dir / "temp"
        else:
            self.base_temp_dir = base_temp_dir
        
        # Ensure base directory exists
        self.base_temp_dir.mkdir(parents=True, exist_ok=True)
    
    def create_temp_dir(self, execution_id: Optional[str] = None) -> Path:
        """
        Create a new temporary directory for agent execution.
        
        Args:
            execution_id: Optional execution ID to use in directory name.
                         If not provided, generates a UUID.
        
        Returns:
            Path to the created temporary directory.
        """
        if execution_id is None:
            execution_id = str(uuid.uuid4())
        
        temp_dir = self.base_temp_dir / f"agent-{execution_id}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        
        return temp_dir
    
    def cleanup_temp_dir(self, temp_dir: Path, force: bool = False) -> bool:
        """
        Clean up a temporary directory.
        
        Args:
            temp_dir: Path to temporary directory to clean up.
            force: If True, forcefully remove even if directory contains important files.
        
        Returns:
            True if cleanup was successful, False otherwise.
        """
        try:
            if not temp_dir.exists():
                return True
            
            # Safety check - only clean up directories under our base temp dir
            if not str(temp_dir).startswith(str(self.base_temp_dir)):
                raise ValueError(f"Refusing to clean up directory outside temp base: {temp_dir}")
            
            # Additional safety check for important files unless force is True
            if not force:
                important_patterns = ['.git', 'node_modules', 'venv', '.env']
                for item in temp_dir.rglob('*'):
                    if any(pattern in item.name for pattern in important_patterns):
                        # Log warning but don't fail - just move to a quarantine folder
                        quarantine_dir = self.base_temp_dir / "quarantine" / temp_dir.name
                        quarantine_dir.parent.mkdir(exist_ok=True)
                        shutil.move(str(temp_dir), str(quarantine_dir))
                        return True
            
            shutil.rmtree(temp_dir, ignore_errors=False)
            return True
            
        except Exception as e:
            # Log the error but don't raise - cleanup failures shouldn't crash the service
            print(f"Failed to cleanup temp directory {temp_dir}: {e}")
            return False
    
    def cleanup_old_dirs(self, max_age_hours: int = 24) -> int:
        """
        Clean up temporary directories older than specified hours.
        
        Args:
            max_age_hours: Maximum age in hours before directories are cleaned up.
        
        Returns:
            Number of directories cleaned up.
        """
        import time
        
        cleaned_count = 0
        current_time = time.time()
        cutoff_time = current_time - (max_age_hours * 3600)
        
        try:
            for temp_dir in self.base_temp_dir.iterdir():
                if temp_dir.is_dir() and temp_dir.name.startswith('agent-'):
                    # Check directory creation time
                    dir_ctime = temp_dir.stat().st_ctime
                    if dir_ctime < cutoff_time:
                        if self.cleanup_temp_dir(temp_dir, force=False):
                            cleaned_count += 1
        except Exception as e:
            print(f"Error during cleanup of old directories: {e}")
        
        return cleaned_count
    
    @asynccontextmanager
    async def temp_dir_context(
        self, 
        execution_id: Optional[str] = None,
        cleanup_on_exit: bool = True
    ) -> AsyncGenerator[Path, None]:
        """
        Async context manager for temporary directory lifecycle.
        
        Args:
            execution_id: Optional execution ID for directory naming.
            cleanup_on_exit: Whether to cleanup directory on context exit.
        
        Yields:
            Path to the temporary directory.
        """
        temp_dir = self.create_temp_dir(execution_id)
        try:
            yield temp_dir
        finally:
            if cleanup_on_exit:
                self.cleanup_temp_dir(temp_dir, force=False)


def get_temp_dir_manager() -> TempDirManager:
    """Get a shared TempDirManager instance."""
    return TempDirManager()


async def create_execution_temp_dir(execution_id: str) -> Path:
    """
    Create a temporary directory for a specific execution.
    
    Args:
        execution_id: Unique execution identifier.
    
    Returns:
        Path to created temporary directory.
    """
    manager = get_temp_dir_manager()
    return manager.create_temp_dir(execution_id)


async def cleanup_execution_temp_dir(temp_dir: Path) -> bool:
    """
    Clean up an execution temporary directory.
    
    Args:
        temp_dir: Path to temporary directory.
    
    Returns:
        True if cleanup successful, False otherwise.
    """
    manager = get_temp_dir_manager()
    return manager.cleanup_temp_dir(temp_dir)