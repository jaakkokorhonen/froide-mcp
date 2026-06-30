"""Froide MCP server."""
try:
    from importlib.metadata import version

    __version__ = version("froide-mcp")
except Exception:  # pragma: no cover
    __version__ = "unknown"
