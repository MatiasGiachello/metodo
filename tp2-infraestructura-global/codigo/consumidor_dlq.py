"""
Arquitectura asincrónica con cola + reintentos + Dead Letter Queue.

Simulación en memoria (sin dependencias) del worker que envía webhooks:
  - Error transitorio (timeout, 5xx)  -> se reintenta con backoff exponencial.
  - Error permanente (payload inválido, 4xx) -> directo a la DLQ.
  - Tras MAX_INTENTOS fallidos -> a la DLQ, sin bloquear al resto de la cola.

En producción la cola es SQS (redrive_policy con maxReceiveCount) o un tópico
"payments.events.dlq" en Kafka.

Ejecutar:  python3 consumidor_dlq.py
"""
import random
from collections import deque
from dataclasses import dataclass, field

MAX_INTENTOS = 4
BACKOFF_BASE = 60  # segundos: 60, 120, 240, 480...


class ErrorTransitorio(Exception):
    pass


class ErrorPermanente(Exception):
    pass


@dataclass
class Mensaje:
    id: str
    comercio_url: str
    intentos: int = 0
    errores: list = field(default_factory=list)


def enviar_webhook(msg: Mensaje):
    if "url-inexistente" in msg.comercio_url:
        raise ErrorPermanente("404 Not Found en el endpoint del comercio")
    if "caido" in msg.comercio_url:
        raise ErrorTransitorio("timeout conectando al comercio")
    if random.random() < 0.3:
        raise ErrorTransitorio("503 Service Unavailable")


def procesar(cola: deque, dlq: list):
    while cola:
        msg = cola.popleft()
        msg.intentos += 1
        try:
            enviar_webhook(msg)
            print(f"OK   {msg.id} entregado (intento {msg.intentos})")
        except ErrorPermanente as e:
            msg.errores.append(str(e))
            dlq.append(msg)
            print(f"DLQ  {msg.id} error permanente: {e}")
        except ErrorTransitorio as e:
            msg.errores.append(str(e))
            if msg.intentos >= MAX_INTENTOS:
                dlq.append(msg)
                print(f"DLQ  {msg.id} agotó {MAX_INTENTOS} intentos")
            else:
                espera = BACKOFF_BASE * 2 ** (msg.intentos - 1)
                print(f"RETRY {msg.id} intento {msg.intentos} falló ({e}); "
                      f"reintento en {espera}s")
                cola.append(msg)  # en SQS: visibility timeout; aquí, al final


if __name__ == "__main__":
    random.seed(7)
    cola = deque([
        Mensaje("evt_1", "https://tienda-a.com/webhooks"),
        Mensaje("evt_2", "https://tienda-caido.com/webhooks"),
        Mensaje("evt_3", "https://tienda-url-inexistente.com/x"),
        Mensaje("evt_4", "https://tienda-b.com/webhooks"),
    ])
    dlq: list[Mensaje] = []
    procesar(cola, dlq)

    print("\nContenido de la Dead Letter Queue (para revisar y re-encolar):")
    for m in dlq:
        print(f"  {m.id} -> {m.comercio_url} | intentos={m.intentos} | {m.errores[-1]}")
