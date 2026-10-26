"""
CQRS: el lado de comandos escribe en el ledger (SQLite en memoria representa
a PostgreSQL) y publica eventos; una proyección consume los eventos y arma
un modelo de lectura desnormalizado (dict que representa a OpenSearch).

Ejecutar:  python3 cqrs_proyeccion.py   (solo librería estándar)
"""
import sqlite3
import uuid
from collections import defaultdict

# ---------------- Lado COMANDOS (escritura, fuente de verdad) ----------------
db = sqlite3.connect(":memory:")
db.executescript("""
CREATE TABLE payments (id TEXT PRIMARY KEY, merchant_id TEXT, amount INTEGER,
                       method TEXT, status TEXT);
CREATE TABLE outbox   (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT,
                       payment_id TEXT, published INTEGER DEFAULT 0);
""")


def crear_pago(merchant_id: str, amount: int, method: str) -> str:
    """Comando: guarda el pago y el evento en la MISMA transacción (outbox)."""
    payment_id = f"pay_{uuid.uuid4().hex[:12]}"
    with db:  # BEGIN ... COMMIT
        db.execute("INSERT INTO payments VALUES (?,?,?,?,?)",
                   (payment_id, merchant_id, amount, method, "approved"))
        db.execute("INSERT INTO outbox (type, payment_id) VALUES (?,?)",
                   ("payment.approved", payment_id))
    return payment_id


def publicar_outbox() -> list[dict]:
    """Relay del outbox -> 'Kafka'. Corre en un proceso aparte."""
    filas = db.execute("""SELECT o.id, o.type, p.id, p.merchant_id, p.amount, p.method
                          FROM outbox o JOIN payments p ON p.id = o.payment_id
                          WHERE o.published = 0 ORDER BY o.id""").fetchall()
    eventos = [{"type": t, "payment_id": pid, "merchant_id": m, "amount": a, "method": me}
               for _, t, pid, m, a, me in filas]
    with db:
        db.executemany("UPDATE outbox SET published = 1 WHERE id = ?",
                       [(f[0],) for f in filas])
    return eventos


# ---------------- Lado CONSULTAS (lectura, desnormalizado) -------------------
modelo_lectura = defaultdict(lambda: {"total": 0, "cantidad": 0,
                                      "por_medio": defaultdict(int)})


def proyectar(evento: dict):
    """Consumidor del tópico: actualiza la vista lista para el dashboard."""
    vista = modelo_lectura[evento["merchant_id"]]
    vista["total"] += evento["amount"]
    vista["cantidad"] += 1
    vista["por_medio"][evento["method"]] += evento["amount"]


def consultar_resumen(merchant_id: str) -> dict:
    """Query: lectura O(1), sin JOINs ni GROUP BY sobre el ledger."""
    v = modelo_lectura[merchant_id]
    return {"total": v["total"], "cantidad": v["cantidad"], "por_medio": dict(v["por_medio"])}


if __name__ == "__main__":
    crear_pago("tienda_a", 12500, "visa")
    crear_pago("tienda_a", 3000, "mastercard")
    crear_pago("tienda_a", 7000, "visa")
    crear_pago("tienda_b", 999, "wallet")

    print("Antes de proyectar (consistencia eventual):", consultar_resumen("tienda_a"))
    for ev in publicar_outbox():
        proyectar(ev)
    print("Después de proyectar:                      ", consultar_resumen("tienda_a"))
