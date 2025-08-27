import asyncio
import sys

from base import ToolError
from bash import BashTool


async def execute_command(**kwargs):
    tool = BashTool()

    if kwargs.get("restart") is None:
        kwargs["restart"] = False
    elif kwargs.get("restart").lower() == "true":
        kwargs["restart"] = True
    else:
        kwargs["restart"] = False

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
