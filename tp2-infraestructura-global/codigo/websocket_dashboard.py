"""
Servicio Realtime: empuja los pagos al dashboard del comercio por WebSocket.

- Cada navegador abre wss://realtime.pagoglobal.com?token=<JWT>.
- Los eventos llegan de Kafka (aquí simulados) y se envían solo a las
  conexiones de ese comercio.
- Con varios pods se usa Redis Pub/Sub para que el evento llegue al pod que
  tiene la conexión abierta.
- En el Graceful Shutdown se cierran las conexiones con código 1001
  ("going away") y el navegador reconecta a otro pod.

Requiere:  pip install websockets
Ejecutar:  python3 websocket_dashboard.py   y abrir la consola del navegador:
           ws = new WebSocket("ws://localhost:8765/?merchant=tienda_a");
           ws.onmessage = e => console.log(e.data)
"""
import asyncio
import json
import random
import signal
from collections import defaultdict
from urllib.parse import parse_qs, urlparse

import websockets

conexiones: dict[str, set] = defaultdict(set)


async def handler(ws):
    # En producción: se valida el JWT del query string y se toma "sub".
    merchant = parse_qs(urlparse(ws.request.path).query).get("merchant", ["?"])[0]
    conexiones[merchant].add(ws)
    try:
        await ws.wait_closed()
    finally:
        conexiones[merchant].discard(ws)


async def consumidor_kafka_simulado():
    while True:
        await asyncio.sleep(2)
        evento = {"type": "payment.approved", "merchant_id": "tienda_a",
                  "amount": random.randint(1000, 50000), "method": "visa ****4242"}
        for ws in list(conexiones[evento["merchant_id"]]):
            await ws.send(json.dumps(evento))


async def main():
    stop = asyncio.get_running_loop().create_future()
    asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, stop.set_result, None)

    async with websockets.serve(handler, "0.0.0.0", 8765) as server:
        tarea = asyncio.create_task(consumidor_kafka_simulado())
        print("Realtime escuchando en ws://localhost:8765")
        await stop
        tarea.cancel()
        # Graceful shutdown: aviso a los clientes para que reconecten a otro pod
        server.close(close_connections=True)  # envía close 1001 Going Away


if __name__ == "__main__":
    asyncio.run(main())
