"""
API entry point.
Run with: python -m backend.main_api
Or with uvicorn: uvicorn backend.main_api:app --port 8000
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

# Proxy corporativo con certificado SSL no estándar.
# truststore inyecta el almacén de Windows en ssl para que Python confíe en él.
import truststore
truststore.inject_into_ssl()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

# Suprimir error cosmetico de Windows: WinError 10013 al cerrar sockets
# ya desconectados (asyncio ProactorEventLoop intenta shutdown en socket cerrado).
class _SuppressWinSocketError(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return "WinError 10013" not in record.getMessage()

logging.getLogger("asyncio").addFilter(_SuppressWinSocketError())

# Suprimir "connection open/closed" de uvicorn -- ruido de protocolo WS,
# los eventos relevantes ya los registra el propio websocket handler.
class _SuppressWsLifecycle(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        return "connection open" not in msg and "connection closed" not in msg

for _logger_name in (
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.protocols.websockets.wsproto_impl",
    "uvicorn",
):
    logging.getLogger(_logger_name).addFilter(_SuppressWsLifecycle())

from backend.api.app import create_app

app = create_app()

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    host = os.getenv("HOST", "0.0.0.0")
    print(f"\nBook Factory API arrancando en http://{host}:{port}")
    print(f"   WebSocket: ws://{host}:{port}/ws/book")
    print(f"   Health:    http://{host}:{port}/health\n")

    uvicorn.run(
        "backend.main_api:app",
        host=host,
        port=port,
        reload=False,
        log_level="info",
        ws_ping_interval=None,
        ws_ping_timeout=None,
    )
