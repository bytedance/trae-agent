import asyncio
from pathlib import Path
import sys

# Add project root to Python path to import trae_agent module
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from trae_agent.tools.ckg_tool import CKGTool
from trae_agent.tools.base import ToolCallArguments


async def main():
    """
    An example of how to use the CKGTool to query the codebase.
    """
    tool = CKGTool()
    codebase_path = str(project_root)

    print(
        f"--- CKG Tool Example ---"
        f"\nThis script will query the codebase at '{codebase_path}'."
        f"\nNote: The first run might be slow as it needs to build the code knowledge graph."
    )
    print("-" * 20)

    # 1. Search for a function
    print("--- 1. Searching for function: 'run' ---")
    search_func_args = ToolCallArguments(
        command="search_function",
        path=codebase_path,
        identifier="run",
    )
    search_func_result = await tool.execute(search_func_args)
    if search_func_result.error:
        print(f"Error: {search_func_result.error}")
    else:
        print(search_func_result.output)
    print("-" * 20)

    # 2. Search for a class
    print("--- 2. Searching for class: 'BashTool' ---")
    search_class_args = ToolCallArguments(
        command="search_class",
        path=codebase_path,
        identifier="BashTool",
    )
    search_class_result = await tool.execute(search_class_args)
    if search_class_result.error:
        print(f"Error: {search_class_result.error}")
    else:
        print(search_class_result.output)
    print("-" * 20)

    # 3. Search for a class method
    print("--- 3. Searching for class method: 'execute' ---")
    search_method_args = ToolCallArguments(
        command="search_class_method",
        path=codebase_path,
        identifier="execute",
        print_body=False,  # Disable printing body to keep output clean
    )
    search_method_result = await tool.execute(search_method_args)
    if search_method_result.error:
        print(f"Error: {search_method_result.error}")
    else:
        print(search_method_result.output)
    print("-" * 20)

    # 4. Search for an identifier that does not exist
    print("--- 4. Searching for non-existent function: 'non_existent_function' ---")
    search_non_existent_args = ToolCallArguments(
        command="search_function",
        path=codebase_path,
        identifier="non_existent_function",
    )
    search_non_existent_result = await tool.execute(search_non_existent_args)
    if search_non_existent_result.error:
        print(f"Error: {search_non_existent_result.error}")
    else:
        print(search_non_existent_result.output)
    print("-" * 20)


if __name__ == "__main__":
    asyncio.run(main())