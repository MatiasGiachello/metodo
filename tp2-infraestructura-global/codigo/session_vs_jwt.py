"""
Session (stateful) vs JWT (stateless), lado a lado.

Requiere:  pip install pyjwt cryptography
Ejecutar:  python3 session_vs_jwt.py
(Las sesiones se guardan en un dict que representa a Redis.)
"""
import secrets
import time

import jwt
from cryptography.hazmat.primitives.asymmetric import ec

# ------------------------------ SESSION -------------------------------------
redis_sesiones: dict[str, dict] = {}  # en producción: Redis con TTL


def login_session(usuario: str) -> str:
    session_id = secrets.token_urlsafe(32)  # ID aleatorio, sin datos adentro
    redis_sesiones[session_id] = {"usuario": usuario, "rol": "admin",
                                  "expira": time.time() + 3600}
    return session_id  # va en cookie HttpOnly; Secure; SameSite=Strict


def validar_session(session_id: str) -> dict | None:
    datos = redis_sesiones.get(session_id)  # consulta al almacén en CADA request
    return datos if datos and datos["expira"] > time.time() else None


def logout_session(session_id: str):
    redis_sesiones.pop(session_id, None)  # revocación INMEDIATA


# -------------------------------- JWT ---------------------------------------
clave_privada = ec.generate_private_key(ec.SECP256R1())  # solo el servidor OAuth
clave_publica = clave_privada.public_key()               # publicada en JWKS


def emitir_jwt(merchant_id: str, scopes: list[str]) -> str:
    ahora = int(time.time())
    claims = {"iss": "https://auth.pagoglobal.com", "aud": "https://api.pagoglobal.com",
              "sub": merchant_id, "scope": " ".join(scopes),
              "iat": ahora, "exp": ahora + 600}  # 10 minutos
    return jwt.encode(claims, clave_privada, algorithm="ES256")


def validar_jwt(token: str) -> dict | None:
    try:  # solo matemática: NO consulta ninguna base de datos
        return jwt.decode(token, clave_publica, algorithms=["ES256"],
                          audience="https://api.pagoglobal.com")
    except jwt.InvalidTokenError:
        return None


if __name__ == "__main__":
    sid = login_session("ana@tienda.com")
    print("Session válida:", validar_session(sid) is not None)
    logout_session(sid)
    print("Session tras logout:", validar_session(sid))  # None: revocada al instante

    token = emitir_jwt("tienda_a", ["payments:write", "payments:read"])
    print("\nJWT:", token[:60], "...")
    print("Claims:", validar_jwt(token))
    print("JWT alterado:", validar_jwt(token[:-4] + "AAAA"))  # firma inválida
    print("Nota: el JWT sigue siendo válido hasta 'exp' aunque el usuario cierre sesión.")
