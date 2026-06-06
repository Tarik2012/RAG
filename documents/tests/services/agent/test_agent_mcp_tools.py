from documents.services.agent.agent import _get_mcp_tools


def test_mcp_tools_loaded():
    names = [t.name for t in _get_mcp_tools()]
    assert "add_numbers" in names
