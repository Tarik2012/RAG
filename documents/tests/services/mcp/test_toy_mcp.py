import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient


def test_toy_mcp_tool_loads_and_runs():
    async def _run():
        client = MultiServerMCPClient(
            {
                "toy": {
                    "command": "python",
                    "args": ["documents/services/mcp/toy_server.py"],
                    "transport": "stdio",
                }
            }
        )
        tools = await client.get_tools()
        names = [t.name for t in tools]
        assert "add_numbers" in names

        add = next(t for t in tools if t.name == "add_numbers")
        result = await add.ainvoke({"a": 2, "b": 3})
        return result

    result = asyncio.run(_run())
    assert "5" in str(result)
