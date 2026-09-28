from typing import override

import mcp

from .base import Tool, ToolCallArguments, ToolExecResult, ToolParameter


def content_blocks_to_text(content: list[mcp.types.ContentBlock]) -> str:
    """Flatten an MCP result's content blocks into text a model can read.

    Only TextContent carries text, and a result is not required to hold any: the other
    block types are named instead of dropped, so a non-text answer stays visible.
    """
    if not content:
        return "(the tool returned no content)"

    parts: list[str] = []
    for block in content:
        match block:
            case mcp.types.TextContent():
                parts.append(block.text)
            case mcp.types.EmbeddedResource():
                resource = block.resource
                match resource:
                    case mcp.types.TextResourceContents():
                        parts.append(resource.text)
                    case _:
                        parts.append(f"[resource without text: {resource.uri}]")
            case mcp.types.ImageContent():
                parts.append(f"[image: {block.mimeType}]")
            case mcp.types.AudioContent():
                parts.append(f"[audio: {block.mimeType}]")
            case mcp.types.ResourceLink():
                parts.append(f"[resource link: {block.name}]")
            case _:
                parts.append(f"[unsupported content: {type(block).__name__}]")
    return "\n".join(parts)


class MCPTool(Tool):
    def __init__(self, client, tool: mcp.types.Tool, model_provider: str | None = None):
        super().__init__(model_provider)
        self.client = client
        self.tool = tool

    @override
    def get_model_provider(self) -> str | None:
        return self._model_provider

    @override
    def get_name(self) -> str:
        return self.tool.name

    @override
    def get_description(self) -> str:
        return self.tool.description

    @override
    def get_parameters(self) -> list[ToolParameter]:
        # For OpenAI models, all parameters must be required=True
        # For other providers, optional parameters can have required=False
        def properties_to_parameter():
            parameters = []
            inputSchema = self.tool.inputSchema
            required = inputSchema.get("required", [])
            properties = inputSchema.get("properties", {})
            for name, prop in properties.items():
                tool_para = ToolParameter(
                    name=name,
                    type=prop["type"],
                    items=prop.get("items", None),
                    description=prop["description"],
                    required=name in required,
                )
                parameters.append(tool_para)
            return parameters

        return properties_to_parameter()

    @override
    async def execute(self, arguments: ToolCallArguments) -> ToolExecResult:
        try:
            output = await self.client.call_tool(self.get_name(), arguments)
            text = content_blocks_to_text(output.content)
            if output.isError:
                return ToolExecResult(output=None, error=text)
            else:
                return ToolExecResult(output=text)

        except Exception as e:
            return ToolExecResult(error=f"Error running mcp tool: {e}", error_code=-1)
