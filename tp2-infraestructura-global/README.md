# TP2 — Infraestructura para una plataforma de pagos electrónicos global

**Materia:** Plataformas de Pagos Electrónicos · **Trabajo individual con exposición oral**

Diseño de la infraestructura de **PagoGlobal**, una pasarela de pagos ficticia que opera en tres regiones (LatAm, Norteamérica y UE), aplicando los 18 conceptos de la consigna y Redis.

## Qué entregar

| Archivo | Para qué |
|---|---|
| `entregables/TP2_PagoGlobal_Informe.docx` | Informe escrito (Word) |
| `entregables/TP2_PagoGlobal_Informe.pdf` | Informe escrito (PDF) |
| `presentacion/TP2_PagoGlobal.pptx` | Presentación para exponer al frente (23 diapositivas, con notas del orador) |
| `entregables/TP2_PagoGlobal_Presentacion.pdf` | La misma presentación en PDF (por si no hay PowerPoint) |
| `presentacion/GUION.md` | Guion, tiempos, demos y preguntas probables |

## Contenido de la carpeta

```
INFORME.md                  Informe completo (fuente del .docx/.pdf)
diagramas/
  arquitectura.svg/.png     Diagrama por capas (generado por generar_arquitectura.py)
  arquitectura.mmd          Versión Mermaid con todas las flechas
  flujo_pago.mmd/.svg/.png  Diagrama de secuencia de un pago
terraform/                  IaC: 3 regiones con un módulo reutilizable
  main.tf, global.tf        Providers, módulos por región, CloudFront, WAF, Route 53
  modules/region/           VPC, EKS, Aurora, Redis, MSK (Kafka), SQS + DLQ, S3, ALB, API Gateway
codigo/                     Ejemplos ejecutables en Python
  webhook_firma.py          Webhooks firmados con HMAC + idempotencia
  graceful_shutdown.py      Apagado elegante ante SIGTERM
  consumidor_dlq.py         Reintentos con backoff + Dead Letter Queue
  uuid_vs_secuencia.py      Secuencia vs UUIDv4 vs UUIDv7
  cqrs_proyeccion.py        CQRS + patrón outbox
  cache_aside_pool.py       Redis: connection pool, cache-aside, idempotencia, rate limit
  session_vs_jwt.py         Session en Redis vs JWT firmado
  presigned_url.py          URLs prefirmadas de S3
  websocket_dashboard.py    Dashboard en tiempo real por WebSocket
  mcp_server.py             Servidor MCP de solo lectura para un agente de IA
presentacion/
  generar_pptx.py           Genera la presentación
  GUION.md                  Guion de exposición
```

## Cómo correr los ejemplos

Los primeros cinco usan solo la librería estándar de Python 3.10+:

```bash
cd codigo
python3 webhook_firma.py
python3 consumidor_dlq.py
python3 uuid_vs_secuencia.py
python3 cqrs_proyeccion.py
python3 graceful_shutdown.py   # luego: curl -X POST localhost:8080/pagos & kill -TERM <pid>
```

El resto necesita `pip install -r codigo/requirements.txt` (y un Redis local para `cache_aside_pool.py`).

## Terraform

```bash
cd terraform
terraform init
terraform plan -var-file=prod.tfvars
```

La configuración pasa `terraform validate` (Terraform 1.9, provider AWS 5.x). Es un diseño académico: aplicarla crearía recursos con costo real en AWS.
