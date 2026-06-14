from documents.services.agent.agent import _get_mcp_tools


def test_mcp_tools_return_list():
    tools = _get_mcp_tools()
    assert isinstance(tools, list)
