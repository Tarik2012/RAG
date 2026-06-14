from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Toy")


@mcp.tool()
def add_numbers(a: int, b: int) -> int:
    """Suma dos números enteros y devuelve el resultado. Úsalo únicamente para sumar dos números."""
    return a + b


if __name__ == "__main__":
    mcp.run(transport="stdio")
