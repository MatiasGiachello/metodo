"""
Secuencia vs UUIDv4 vs UUIDv7.

- Secuencia: compacta y ordenada, pero predecible (enumeración / IDOR) y
  requiere un generador central.
- UUIDv4: aleatorio; seguro, pero inserta en posiciones aleatorias del índice.
- UUIDv7 (RFC 9562): 48 bits de timestamp en ms + bits aleatorios. No es
  adivinable y crece casi en orden -> índices B-tree eficientes.

Ejecutar:  python3 uuid_vs_secuencia.py   (solo librería estándar)
"""
import itertools
import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Implementación mínima de UUIDv7 (Python 3.14+ trae uuid.uuid7())."""
    ts_ms = time.time_ns() // 1_000_000
    rand = int.from_bytes(os.urandom(10), "big")  # 80 bits aleatorios
    rand_a = rand >> 68                           # 12 bits
    rand_b = rand & ((1 << 62) - 1)               # 62 bits
    valor = ((ts_ms & ((1 << 48) - 1)) << 80      # 48 bits de tiempo (ms)
             | 0x7 << 76                          # versión 7
             | rand_a << 64
             | 0b10 << 62                         # variante RFC 9562
             | rand_b)
    return uuid.UUID(int=valor)


def fraccion_ordenada(ids) -> float:
    pares = list(zip(ids, ids[1:]))
    return sum(a < b for a, b in pares) / len(pares)


if __name__ == "__main__":
    secuencia = itertools.count(1_045_890)
    print("Secuencia :", [next(secuencia) for _ in range(3)], "<- el siguiente es obvio")

    v4 = [str(uuid.uuid4()) for _ in range(1000)]
    v7 = []
    for _ in range(1000):
        v7.append(str(uuid7()))
        time.sleep(0.0005)

    print("UUIDv4    :", v4[0])
    print("UUIDv7    :", v7[0], f"(versión {uuid.UUID(v7[0]).version})")
    print(f"\nInserciones 'al final del índice' (orden creciente):")
    print(f"  UUIDv4: {fraccion_ordenada(v4):.0%}  -> páginas del índice se fragmentan")
    print(f"  UUIDv7: {fraccion_ordenada(v7):.0%}  -> casi como una secuencia (solo se desordena dentro del mismo milisegundo)")
    print(f"\nID público de un pago en PagoGlobal: pay_{uuid7().hex}")
