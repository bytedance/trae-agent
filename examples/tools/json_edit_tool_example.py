import asyncio
import json
import os
from pathlib import Path
import sys

# Add project root to Python path to import trae_agent module
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from trae_agent.tools.json_edit_tool import JSONEditTool
from trae_agent.tools.base import ToolCallArguments


async def main():
    """
    An example of how to use the JSONEditTool to perform JSON file operations.
    """
    tool = JSONEditTool()
    test_file_path = Path(__file__).parent / "test_data.json"
    test_file_path_str = str(test_file_path.absolute())

    # Initial JSON data
    initial_data = {
        "name": "test-project",
        "version": "1.0.0",
        "dependencies": {"libA": "1.0", "libB": "2.0"},
    }

    # 1. Create a JSON file for testing
    print("--- 1. Creating test JSON file ---")
    with open(test_file_path, "w") as f:
        json.dump(initial_data, f, indent=2)
    print(f"File created at: {test_file_path_str}")
    print("Initial content:")
    print(test_file_path.read_text())
    print("-" * 20)

    # 2. Add a new key-value pair at the root
    print("--- 2. Testing 'add' operation (root level) ---")
    add_args = ToolCallArguments(
        operation="add",
        file_path=test_file_path_str,
        json_path="$.author",
        value="Gemini",
    )
    add_result = await tool.execute(add_args)
    if add_result.error:
        print(f"Error: {add_result.error}")
    else:
        print(add_result.output)
    print("Current content:")
    print(test_file_path.read_text())
    print("-" * 20)

    # 3. Replace an existing value
    print("--- 3. Testing 'set' operation ---")
    replace_args = ToolCallArguments(
        operation="set",
        file_path=test_file_path_str,
        json_path="$.version",
        value="1.1.0",
    )
    replace_result = await tool.execute(replace_args)
    if replace_result.error:
        print(f"Error: {replace_result.error}")
    else:
        print(replace_result.output)
    print("Current content:")
    print(test_file_path.read_text())
    print("-" * 20)

    # 4. Add a new dependency (nested add)
    print("--- 4. Testing 'add' operation (nested) ---")
    add_nested_args = ToolCallArguments(
        operation="add",
        file_path=test_file_path_str,
        json_path="$.dependencies.libC",
        value="3.0",
    )
    add_nested_result = await tool.execute(add_nested_args)
    if add_nested_result.error:
        print(f"Error: {add_nested_result.error}")
    else:
        print(add_nested_result.output)
    print("Current content:")
    print(test_file_path.read_text())
    print("-" * 20)

    # 5. Delete a dependency
    print("--- 5. Testing 'remove' operation ---")
    delete_args = ToolCallArguments(
        operation="remove",
        file_path=test_file_path_str,
        json_path="$.dependencies.libA",
    )
    delete_result = await tool.execute(delete_args)
    if delete_result.error:
        print(f"Error: {delete_result.error}")
    else:
        print(delete_result.output)
    print("Current content:")
    print(test_file_path.read_text())
    print("-" * 20)

    # Clean up the test file
    os.remove(test_file_path)
    print(f"Cleaned up test file: {test_file_path_str}")


if __name__ == "__main__":
    asyncio.run(main())