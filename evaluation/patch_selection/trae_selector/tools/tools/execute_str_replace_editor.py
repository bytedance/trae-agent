import os
import sys
import json
import pickle
import asyncio
from pathlib import Path
from edit import EditTool
from base import ToolError


async def execute_command(**kwargs):
    tool = EditTool()

    if os.path.exists('file_history.pkl'):
        with open('file_history.pkl', 'rb') as file:
            tool._file_history = pickle.load(file)    

    kwargs["path"] = Path(kwargs["path"]) if "path" in kwargs and kwargs["path"] else None
    
    try:
        kwargs["view_range"] = json.loads(kwargs["view_range"]) if kwargs.get("view_range") is not None else None
    except json.JSONDecodeError:
        pass
    
    try:
        kwargs["insert_line"] = int(kwargs["insert_line"]) if kwargs.get("insert_line") is not None else None
    except:
        pass
    
    try:
        result = await tool(
            command=kwargs.get("command"),
            path=kwargs.get("path"),
            file_text=kwargs.get("file_text"),
            view_range=kwargs.get("view_range"),
            insert_line=kwargs.get("insert_line"),
            old_str=kwargs.get("old_str"),
            new_str=kwargs.get("new_str")
        )
        with open('file_history.pkl', 'wb') as file:
            pickle.dump(tool._file_history, file)
        return_content = ""
        if result.output is not None:
            return_content += result.output
        if result.error is not None:
            return_content += "\n" + result.error
        return 0, return_content
    except ToolError as e:
        return -1, e


if __name__ == "__main__":
    args = sys.argv[1:]
    kwargs = {}
    it = iter(args)
    for arg in it:
        if arg.startswith('--'):
            key = arg.lstrip('--')
            try:
                value = next(it)
                kwargs[key] = value
            except StopIteration:
                kwargs[key] = None
    status, output = asyncio.run(execute_command(**kwargs))
    print(f"Tool Call Status: {status}")
    print(output)