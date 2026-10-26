"""
Webhooks firmados con HMAC-SHA256 (emisor = PagoGlobal, receptor = comercio).

- El emisor firma "timestamp.payload" con un secreto compartido por comercio.
- El receptor verifica la firma en tiempo constante y rechaza mensajes viejos
  (protección contra replay attacks).
- El receptor es idempotente: si el mismo event_id llega dos veces (entrega
  "at-least-once"), lo procesa una sola vez.

Ejecutar:  python3 webhook_firma.py   (solo librería estándar)
"""
import hashlib
import hmac
import json
import time
import uuid

TOLERANCIA_SEGUNDOS = 300  # 5 minutos


# ----------------------------- Lado PagoGlobal ------------------------------
def firmar(payload: bytes, secreto: str, timestamp: int) -> str:
    mensaje = f"{timestamp}.".encode() + payload
    firma = hmac.new(secreto.encode(), mensaje, hashlib.sha256).hexdigest()
    return f"t={timestamp},v1={firma}"


def construir_webhook(evento: dict, secreto: str) -> tuple[dict, bytes]:
    body = json.dumps(evento, separators=(",", ":")).encode()
    headers = {
        "Content-Type": "application/json",
        "PagoGlobal-Signature": firmar(body, secreto, int(time.time())),
    }
    return headers, body


# ------------------------------ Lado comercio -------------------------------
eventos_procesados: set[str] = set()  # en producción: tabla con UNIQUE(event_id)


def verificar(headers: dict, body: bytes, secreto: str) -> bool:
    partes = dict(p.split("=", 1) for p in headers["PagoGlobal-Signature"].split(","))
    timestamp, firma_recibida = int(partes["t"]), partes["v1"]

    if abs(time.time() - timestamp) > TOLERANCIA_SEGUNDOS:
        return False  # demasiado viejo: posible replay

    esperada = hmac.new(secreto.encode(), f"{timestamp}.".encode() + body,
                        hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperada, firma_recibida)  # tiempo constante


def recibir_webhook(headers: dict, body: bytes, secreto: str) -> int:
    if not verificar(headers, body, secreto):
        return 401
    evento = json.loads(body)
    if evento["id"] in eventos_procesados:
        print(f"  evento {evento['id']} duplicado -> se ignora (idempotencia)")
        return 200  # 200 igual, para que el emisor no reintente
    eventos_procesados.add(evento["id"])
    print(f"  procesando {evento['type']}: pedido {evento['data']['order_id']} -> PAGADO")
    return 200


if __name__ == "__main__":
    secreto = "whsec_demo_123"
    evento = {
        "id": f"evt_{uuid.uuid4().hex}",
        "type": "payment.approved",
        "data": {"payment_id": "pay_0192c7a2", "order_id": "A-1001", "amount": 12500},
    }
    headers, body = construir_webhook(evento, secreto)

    print("1) Entrega normal:", recibir_webhook(headers, body, secreto))
    print("2) Reintento del mismo evento:", recibir_webhook(headers, body, secreto))

    alterado = body.replace(b"12500", b"1")
    print("3) Payload alterado por un atacante:", recibir_webhook(headers, alterado, secreto))
