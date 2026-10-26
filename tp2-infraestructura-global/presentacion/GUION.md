# Guion de exposición — TP2 PagoGlobal

**Duración objetivo:** 15 minutos + 5 de preguntas. Cada diapositiva tiene sus notas del orador en el `.pptx` (vista “Moderador” en PowerPoint).

## Reparto del tiempo

| Bloque | Diapositivas | Tiempo |
|---|---|---|
| Presentación del caso y requisitos | 1–3 | 2 min |
| Arquitectura completa + recorrido de un pago | 4–5 | 3 min |
| Entrada e infraestructura: Terraform, CDN/proxy, LB vs Gateway | 6–8 | 2 min |
| Identidad e integraciones: OAuth/JWT/Session, API/Webhook/MCP, WS | 9–11 | 2,5 min |
| Asincronía: Kafka/colas, DLQ, CQRS | 12–14 | 2,5 min |
| Datos y operación: Redis, Pool, UUID, Presigned, Graceful Shutdown | 15–19 | 2 min |
| Global, Black Friday, conclusiones | 20–22 | 1 min |

**Consejo:** la diapositiva 5 (recorrido de un pago) es la columna vertebral. Si el tiempo se acorta, contar bien el recorrido y después ir rápido por los conceptos, porque todos aparecen en ese recorrido.

## Frase de apertura

> “Diseñé la infraestructura de PagoGlobal, una pasarela de pagos que opera en tres continentes. Elegí pagos porque es donde más duele equivocarse: un cobro no se puede duplicar ni perder, y cada minuto caído es plata que los comercios no cobran.”

## Frase de cierre

> “No hay una tecnología correcta, hay decisiones con costos. Lo importante es elegirlas conscientemente y poder justificarlas, y eso es lo que traté de mostrar con cada componente.”

## Demos opcionales (si se puede usar la compu)

Desde `codigo/`, todas sin instalar nada:

```bash
python3 webhook_firma.py      # firma HMAC: el webhook alterado se rechaza con 401
python3 consumidor_dlq.py     # reintentos con backoff y mensajes que terminan en la DLQ
python3 uuid_vs_secuencia.py  # UUIDv7 ordenado vs UUIDv4 aleatorio
python3 cqrs_proyeccion.py    # consistencia eventual: antes y después de proyectar
python3 graceful_shutdown.py  # en otra terminal: curl -X POST localhost:8080/pagos & kill -TERM <pid>
```

## Preguntas probables y cómo responderlas

**¿Por qué Kafka y además SQS? ¿No alcanza con uno?**
Kafka es para *eventos de dominio* que leen muchos consumidores y que se pueden volver a leer. SQS es para *tareas* individuales con reintento por mensaje y DLQ nativa (cada webhook a cada comercio). Se podría hacer todo con Kafka, pero manejar reintentos con demoras distintas por mensaje es más simple con SQS.

**¿Qué pasa si Kafka está caído cuando se aprueba un pago?**
Nada se pierde: el evento quedó en la tabla *outbox* en la misma transacción que el pago. Cuando Kafka vuelve, el relay lo publica. El comprador ya recibió su respuesta.

**¿Y si el comercio recibe el mismo webhook dos veces?**
Es esperable (entrega *at-least-once*). El comercio guarda el `event_id` y si ya lo procesó lo ignora. Así lo hacen Stripe y Mercado Pago.

**¿Cómo evitan cobrar dos veces si el cliente reintenta?**
Con la `Idempotency-Key`: el cliente manda un UUID por operación; Redis guarda la clave con `SET NX`. El segundo intento, aunque el Load Balancer lo mande a otro servidor, encuentra la clave y recibe la misma respuesta.

**¿Por qué no solo JWT, que es más moderno?**
Porque un JWT no se puede revocar antes de que expire sin agregar una lista negra (que vuelve a tener estado). Para el dashboard, donde una cuenta robada se tiene que cortar ya, conviene la sesión en Redis.

**¿Por qué UUIDv7 y no UUIDv4?**
Los dos son imposibles de adivinar, pero el v4 es completamente aleatorio y fragmenta el índice B-tree de la base (cada inserción va a una página distinta). El v7 empieza con el timestamp, así que las inserciones van casi siempre al final, como una secuencia.

**¿Qué diferencia hay entre proxy inverso, Load Balancer y API Gateway?**
Proxy inverso es el concepto general (alguien que recibe por el servidor). El Load Balancer es un proxy inverso cuyo trabajo es repartir entre instancias iguales. El API Gateway es un proxy inverso especializado en APIs que rutea entre servicios distintos y aplica políticas.

**¿Qué pasa si se cae una región entera?**
Route 53 deja de mandarle tráfico por los health checks. Aurora Global Database tiene una copia en otra región con menos de un segundo de retraso; se promueve y en menos de 15 minutos los comercios de esa región vuelven a operar desde la secundaria.

**¿Cómo cumplen PCI DSS?**
Tokenizando el número de tarjeta apenas entra, en un servicio aislado con HSM. El resto de la plataforma solo ve tokens, lo que deja la mayoría de los servicios fuera del alcance de la auditoría.

**¿CQRS no complica todo?**
Sí, agrega complejidad y consistencia eventual. Se justifica porque las lecturas pesadas (reportes) competirían con los cobros en la misma base. Para el estado exacto de un pago se sigue leyendo del lado de escritura.

**¿Para qué sirve MCP en una plataforma de pagos?**
Para que un asistente de IA atienda consultas de comercios (“¿por qué se rechazó este pago?”) con datos reales, mediante herramientas estándar y de solo lectura, autenticadas con OAuth. Nunca se expone una herramienta que mueva dinero.
