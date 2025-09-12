import asyncio
import os
from pathlib import Path

# Since the script is in examples, we need to add the project root to the python path
# to import the trae_agent module.
import sys

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from trae_agent.tools.edit_tool import TextEditorTool
from trae_agent.tools.base import ToolCallArguments


async def main():
    """
    An example of how to use the TextEditorTool to perform file operations.
    """
    tool = TextEditorTool()
    test_file_path = Path(__file__).parent / "test_file.txt"
    test_file_path_str = str(test_file_path.absolute())

    # 1. Create a file
    print("--- 1. Testing 'create' command ---")
    create_args = ToolCallArguments(
        command="create",
        path=test_file_path_str,
        file_text="Hello, world!\nThis is a test file.\n",
    )
    create_result = await tool.execute(create_args)
    print(create_result.output)
    print("-" * 20)

    # 2. View the file
    print("--- 2. Testing 'view' command ---")
    view_args = ToolCallArguments(command="view", path=test_file_path_str)
    view_result = await tool.execute(view_args)
    print(view_result.output)
    print("-" * 20)

    # 3. Replace a string in the file
    print("--- 3. Testing 'str_replace' command ---")
    replace_args = ToolCallArguments(
        command="str_replace",
        path=test_file_path_str,
        old_str="world",
        new_str="Python",
    )
    replace_result = await tool.execute(replace_args)
    print(replace_result.output)
    print("-" * 20)

    # 4. View the file again to see the replacement
    print("--- 4. Viewing file after replacement ---")
    view_result_after_replace = await tool.execute(view_args)
    print(view_result_after_replace.output)
    print("-" * 20)

    # 5. Insert a string into the file
    print("--- 5. Testing 'insert' command ---")
    insert_args = ToolCallArguments(
        command="insert",
        path=test_file_path_str,
        insert_line=1,
        new_str="This is a new line.",
    )
    insert_result = await tool.execute(insert_args)
    print(insert_result.output)
    print("-" * 20)

    # 6. View the file again to see the insertion
    print("--- 6. Viewing file after insertion ---")
    view_result_after_insert = await tool.execute(view_args)
    print(view_result_after_insert.output)
    print("-" * 20)

    # Clean up the test file
    os.remove(test_file_path)
    print(f"Cleaned up test file: {test_file_path_str}")


if __name__ == "__main__":
    asyncio.run(main())