"""Punto de entrada del servidor MCP para clientes como Claude Desktop.

Toda la lógica vive en el paquete mcp_mef/ (compartida con el CLI `mef`).
Este archivo se mantiene para no romper configuraciones existentes de
claude_desktop_config.json que apuntan a "main.py".
"""
from mcp_mef.server import mcp

if __name__ == "__main__":
    mcp.run(transport='stdio')
