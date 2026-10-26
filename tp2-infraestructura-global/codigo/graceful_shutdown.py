"""
Graceful Shutdown de un servicio HTTP.

Al recibir SIGTERM (lo que envía Kubernetes al reemplazar un pod):
  1. /ready empieza a responder 503 -> el Load Balancer deja de mandarle tráfico.
  2. Se dejan de aceptar conexiones nuevas.
  3. Se espera a que terminen las peticiones en curso (con un tope de tiempo).
  4. Se cierran recursos (pool de BD, productor de Kafka) y se sale con código 0.

Ejecutar:  python3 graceful_shutdown.py
Probar:    curl -X POST localhost:8080/pagos &   y enseguida   kill -TERM <pid>
           -> el pago en curso termina bien antes de que el proceso se apague.
"""
import os
import signal
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEMORA_DESREGISTRO = 5  # segundos (equivale al preStop "sleep" de Kubernetes)
apagando = threading.Event()
en_curso = 0
lock = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/ready":
            # Readiness probe: durante el apagado devuelve 503
            self._responder(503 if apagando.is_set() else 200, b"")
        else:
            self._responder(404, b"")

    def do_POST(self):
        global en_curso
        if apagando.is_set():
            self._responder(503, b'{"error":"apagando, reintente"}')
            return
        with lock:
            en_curso += 1
        try:
            time.sleep(3)  # simula autorizar con la red de tarjetas + guardar en BD
            self._responder(201, b'{"status":"approved"}')
        finally:
            with lock:
                en_curso -= 1

    def _responder(self, codigo, body):
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def cerrar_recursos():
    print("[shutdown] cerrando pool de conexiones a la BD...")
    print("[shutdown] flush del productor de Kafka y commit de offsets...")


def main():
    server = ThreadingHTTPServer(("0.0.0.0", 8080), Handler)
    server.daemon_threads = False  # no matar hilos con peticiones en curso

    def detener_listener():
        # Se sigue escuchando unos segundos respondiendo 503 en /ready para que
        # el Load Balancer note el cambio y saque al pod de rotación.
        time.sleep(DEMORA_DESREGISTRO)
        server.shutdown()

    def on_sigterm(signum, frame):
        print(f"[shutdown] señal {signum} recibida, marcando como no listo")
        apagando.set()
        # shutdown() debe llamarse desde otro hilo distinto al de serve_forever
        threading.Thread(target=detener_listener).start()

    signal.signal(signal.SIGTERM, on_sigterm)
    signal.signal(signal.SIGINT, on_sigterm)

    print(f"Servicio de pagos escuchando en :8080 (pid {os.getpid()})")
    server.serve_forever()  # vuelve cuando se llama a shutdown()

    limite = time.time() + 30  # < terminationGracePeriodSeconds de Kubernetes
    while en_curso > 0 and time.time() < limite:
        print(f"[shutdown] esperando {en_curso} petición(es) en curso...")
        time.sleep(0.5)

    server.server_close()
    cerrar_recursos()
    print("[shutdown] apagado limpio")


if __name__ == "__main__":
    main()
