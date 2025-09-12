import asyncio
from pathlib import Path
import sys

# Add project root to Python path to import trae_agent module
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from trae_agent.tools.run import run


async def main():
    """
    An example of how to use the run function to execute shell commands.
    """
    # 1. Define the command to be executed
    command_to_run = "ls -l"
    print(f"--- 1. Executing command: '{command_to_run}' ---")

    # 2. Execute the command using the run function
    return_code, stdout, stderr = await run(command_to_run)

    # 3. Print the results
    print(f"Return Code: {return_code}")
    print("-" * 20)

    if stdout:
        print("--- Standard Output ---")
        print(stdout)
        print("-" * 20)

    if stderr:
        print("--- Standard Error ---")
        print(stderr)
        print("-" * 20)

    # Example of a command that produces an error
    error_command = "ls non_existent_directory"
    print(f"--- 2. Executing command that fails: '{error_command}' ---")

    return_code, stdout, stderr = await run(error_command)

    print(f"Return Code: {return_code}")
    print("-" * 20)

    if stdout:
        print("--- Standard Output ---")
        print(stdout)
        print("-" * 20)

    if stderr:
        print("--- Standard Error ---")
        print(stderr)
        print("-" * 20)


if __name__ == "__main__":
    asyncio.run(main())