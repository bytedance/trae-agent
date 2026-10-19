import pytest
from mcp.types import Tool

from trae_agent.tools.mcp_tool import MCPTool


@pytest.mark.parametrize("provider", [None, "anthropic", "openai"])
def test_missing_parameter_description_does_not_break_discovery(provider):
    schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "limit": {"type": "integer", "description": "Maximum results"},
        },
        "required": ["query"],
    }
    tool = MCPTool(None, Tool(name="search", inputSchema=schema), provider)

    definition = tool.json_definition()

    assert definition["description"] == ""
    parameters = definition["parameters"]
    assert parameters["properties"]["query"]["description"] == ""
    assert parameters["properties"]["limit"]["description"] == "Maximum results"
    assert "query" in parameters["required"]
    assert ("limit" in parameters["required"]) == (provider == "openai")


def test_provided_tool_description_is_preserved():
    tool = MCPTool(
        None, Tool(name="search", description="Search documents", inputSchema={"type": "object"})
    )
    assert tool.get_description() == "Search documents"
