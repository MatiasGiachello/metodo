"""
Redis en PagoGlobal: Connection Pool + cache-aside + idempotencia + rate limit.

Requiere:  pip install redis      y un Redis local:  docker run -p 6379:6379 redis:7
Ejecutar:  python3 cache_aside_pool.py
"""
import json
import time

import redis
from redis import ConnectionPool

# Connection Pool: las conexiones TCP se abren una vez y se reutilizan.
# Si las 20 están ocupadas, se espera hasta 0.2 s y luego se falla rápido.
pool = ConnectionPool(host="localhost", port=6379, db=0, max_connections=20,
                      socket_timeout=0.2, health_check_interval=30)
r = redis.Redis(connection_pool=pool)


# --------------------------- 1. Cache-aside ---------------------------------
def config_comercio(merchant_id: str) -> dict:
    clave = f"merchant:{merchant_id}:config"
    try:
        if (cache := r.get(clave)) is not None:
            return json.loads(cache)                      # CACHE HIT
    except redis.RedisError:
        return leer_de_postgres(merchant_id)              # degradación elegante
    dato = leer_de_postgres(merchant_id)                  # CACHE MISS
    r.set(clave, json.dumps(dato), ex=300)                # TTL 5 minutos (= SETEX)
    return dato


def leer_de_postgres(merchant_id: str) -> dict:
    time.sleep(0.05)  # simula consulta (que también usaría un pool, ej. psycopg_pool)
    return {"merchant_id": merchant_id, "moneda": "ARS", "3ds_obligatorio": True}


# --------------------------- 2. Idempotencia --------------------------------
def crear_pago(idempotency_key: str, monto: int) -> dict:
    clave = f"idem:{idempotency_key}"
    # SET NX: solo la PRIMERA petición con esa clave obtiene el "lock".
    if not r.set(clave, "EN_PROCESO", nx=True, ex=86400):
        guardado = r.get(clave)
        if guardado == b"EN_PROCESO":
            return {"error": "409 petición idéntica en curso"}
        return json.loads(guardado)  # mismo resultado, sin cobrar de nuevo
    resultado = {"id": "pay_0192c7a2", "monto": monto, "status": "approved"}
    r.set(clave, json.dumps(resultado), ex=86400)
    return resultado


# --------------------------- 3. Rate limiting -------------------------------
def permitir(merchant_id: str, limite_por_segundo: int = 1000) -> bool:
    clave = f"rl:{merchant_id}:{int(time.time())}"
    with r.pipeline() as p:            # una sola ida y vuelta de red
        p.incr(clave)
        p.expire(clave, 2)
        cantidad, _ = p.execute()
    return cantidad <= limite_por_segundo


if __name__ == "__main__":
    for i in (1, 2):
        t0 = time.perf_counter()
        config_comercio("tienda_a")
        print(f"config_comercio llamada {i}: {(time.perf_counter() - t0) * 1000:.1f} ms")

    print("pago:", crear_pago("4f1c...-mismo-uuid", 12500))
    print("reintento del cliente:", crear_pago("4f1c...-mismo-uuid", 12500))
    print("rate limit OK:", permitir("tienda_a"))
    print("conexiones creadas en el pool:", len(pool._available_connections)
          + len(pool._in_use_connections))
