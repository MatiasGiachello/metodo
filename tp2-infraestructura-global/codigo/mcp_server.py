"""
Servidor MCP (Model Context Protocol) de solo lectura para el agente de
soporte de PagoGlobal. El LLM descubre estas herramientas y las invoca de
forma estandarizada; nunca recibe una herramienta que mueva dinero.

Requiere:  pip install "mcp[cli]"
Ejecutar:  python3 mcp_server.py      (transporte stdio)
Se registra en un cliente MCP (Claude Desktop, Claude Code, etc.) como:
  {"mcpServers": {"pagoglobal": {"command": "python3", "args": ["mcp_server.py"]}}}
"""
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pagoglobal-soporte")

# En producción estas funciones llaman al servicio de Consultas (lado lectura
# de CQRS) con un token OAuth del comercio con scope "payments:read".
PAGOS = {
    "pay_0192c7a2": {"status": "declined", "amount": 12500, "method": "visa ****4242",
                     "decline_code": "insufficient_funds", "3ds": "authenticated"},
}

MOTIVOS = {
    "insufficient_funds": "El banco emisor rechazó por fondos insuficientes. "
                          "Sugerir otro medio de pago al comprador.",
    "do_not_honor": "Rechazo genérico del emisor; el comprador debe contactar a su banco.",
}


@mcp.tool()
def buscar_pago(payment_id: str) -> dict:
    """Devuelve estado, monto y medio de pago de un pago del comercio."""
    return PAGOS.get(payment_id, {"error": "pago no encontrado"})


@mcp.tool()
def motivo_rechazo(payment_id: str) -> str:
    """Explica en lenguaje simple por qué se rechazó un pago."""
    pago = PAGOS.get(payment_id)
    if not pago or pago["status"] != "declined":
        return "El pago no está rechazado."
    return MOTIVOS.get(pago["decline_code"], "Motivo no catalogado.")


if __name__ == "__main__":
    mcp.run()
