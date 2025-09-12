import asyncio
from pathlib import Path
import sys

# Add project root to Python path to import trae_agent module
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from trae_agent.tools.bash_tool import BashTool
from trae_agent.tools.base import ToolCallArguments


async def main():
    """
    An example of how to use the BashTool to execute shell commands.
    """
    tool = BashTool()

    # 1. Execute a simple echo command
    echo_command = 'echo "Hello from BashTool!"'
    print(f"--- 1. Executing command: '{echo_command}' ---")
    echo_args = ToolCallArguments(command=echo_command)
    echo_result = await tool.execute(echo_args)

    if echo_result.error:
        print(f"Error: {echo_result.error}")
    else:
        print("--- Output ---")
        print(echo_result.output)
    print("-" * 20)

    # 2. Execute a command to list files
    ls_command = "ls -la"
    print(f"--- 2. Executing command: '{ls_command}' ---")
    ls_args = ToolCallArguments(command=ls_command)
    ls_result = await tool.execute(ls_args)

    if ls_result.error:
        print(f"Error: {ls_result.error}")
    else:
        print("--- Output ---")
        print(ls_result.output)
    print("-" * 20)

    # 3. Execute a command that fails
    error_command = "cat non_existent_file.txt"
    print(f"--- 3. Executing a failing command: '{error_command}' ---")
    error_args = ToolCallArguments(command=error_command)
    error_result = await tool.execute(error_args)

    # The BashTool is designed to pipe stderr to stdout, so errors appear in the output
    if error_result.output:
        print("--- Output (contains error) ---")
        print(error_result.output)
    print("-" * 20)


if __name__ == "__main__":
    asyncio.run(main())