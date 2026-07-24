import asyncio
import sys

from base import ToolError
from bash import BashTool


async def execute_command(**kwargs):
    tool = BashTool()

    restart_val = kwargs.get("restart")
    if restart_val is None:
        kwargs["restart"] = False
    elif isinstance(restart_val, bool):
        kwargs["restart"] = restart_val
    elif isinstance(restart_val, str):
        kwargs["restart"] = restart_val.lower() == "true"
    else:
        kwargs["restart"] = bool(restart_val)

    try:
        result = await tool(command=kwargs.get("command"), restart=kwargs.get("restart"))
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
        if arg.startswith("--"):
            key = arg.lstrip("-")
            try:
                value = next(it)
                kwargs[key] = value
            except StopIteration:
                kwargs[key] = None
    status, output = asyncio.run(execute_command(**kwargs))
    print(f"Tool Call Status: {status}")
    print(output)
