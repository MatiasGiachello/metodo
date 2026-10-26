"""
Genera diagramas/arquitectura.svg: vista por capas de la infraestructura de
PagoGlobal. Ejecutar:  python3 generar_arquitectura.py
"""
from html import escape

W, H = 1700, 1080
MAIN_X, MAIN_W = 140, 1370   # área de las capas
LANE_X = MAIN_X + MAIN_W + 10  # carril derecho para la flecha app -> datos

CAPAS = [
    ("1 · Clientes", "#e8f1ff", "#2f6fd6", "#0b2a5b", [
        ("Comprador", "web / app · HTTPS + JWT"),
        ("Backend del comercio", "API REST · recibe Webhooks"),
        ("Dashboard del comercio", "Session (cookie) · WebSocket"),
        ("Agente IA de soporte", "LLM · MCP"),
    ]),
    ("2 · Edge global", "#fff4e0", "#d98a00", "#5a3a00", [
        ("Route 53", "DNS por latencia · health checks"),
        ("CDN CloudFront", "caché en +400 PoPs · WAF · Shield DDoS"),
        ("S3 estáticos", "JS/CSS del checkout (origen privado)"),
    ]),
    ("3 · Entrada regional", "#f1e8ff", "#7a3fd6", "#2e0b5b", [
        ("Load Balancer (ALB)", "proxy inverso · TLS · health checks"),
        ("API Gateway", "valida JWT · rate limit · ruteo /v1"),
        ("OAuth 2.0 / OIDC", "emite JWT · JWKS · scopes"),
    ]),
    ("4 · Microservicios en Kubernetes (EKS) — Graceful Shutdown en todos los pods",
     "#e6f7ee", "#1f9d55", "#0b3d22", [
        ("Payments", "COMMANDS · idempotencia"),
        ("Consultas", "QUERIES (CQRS)"),
        ("Notificaciones", "Webhooks firmados HMAC"),
        ("Realtime", "WebSocket"),
        ("Archivos", "Presigned URL"),
        ("Servidor MCP", "herramientas solo lectura"),
    ]),
    ("5 · Mensajería asincrónica", "#fff0f6", "#c2185b", "#5b0b2e", [
        ("Apache Kafka (MSK)", "payments.events · partición = merchant_id"),
        ("SQS webhooks", "reintentos con backoff"),
        ("Dead Letter Queue", "fallidos tras 8 intentos · alarma"),
    ]),
    ("6 · Datos", "#fdeaea", "#c0392b", "#5b0b0b", [
        ("Redis", "caché · sesiones · idempotencia · rate limit"),
        ("PgBouncer", "Connection Pool"),
        ("Aurora PostgreSQL", "ledger · IDs UUIDv7 · Global DB"),
        ("OpenSearch", "modelo de lectura (CQRS)"),
        ("S3 privado", "reportes · evidencias"),
    ]),
]

# Flechas horizontales dentro de una capa: (capa, desde, hasta, etiqueta)
FLECHAS_INTERNAS = [
    (1, 1, 2, ""), (2, 0, 1, ""), (2, 1, 2, ""),
    (4, 0, 1, ""), (4, 1, 2, "falla"), (5, 1, 2, ""),
]
# Flechas entre capas (en el hueco debajo de la capa i): (capa, x relativa, texto, doble)
FLECHAS_ENTRE = [
    (0, 0.30, "HTTPS", False),
    (1, 0.50, "/v1 sin caché → región más cercana", False),
    (2, 0.50, "ruteo por path", False),
    (3, 0.30, "publica eventos (outbox) / consume", True),
]

BAND_Y0, BAND_H, GAP = 70, 128, 30
BOX_H = 74
FONT = "Arial, Helvetica, sans-serif"

out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
       f'viewBox="0 0 {W} {H}" font-family="{FONT}">',
       '<defs><marker id="a" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
       'markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" '
       'fill="#333"/></marker></defs>',
       f'<rect width="{W}" height="{H}" fill="#ffffff"/>',
       f'<text x="{W/2}" y="40" text-anchor="middle" font-size="26" font-weight="bold" '
       f'fill="#111">PagoGlobal — Infraestructura de un sitio de pagos global</text>']


def band_y(i):
    return BAND_Y0 + i * (BAND_H + GAP)


def box_geom(i, j):
    n = len(CAPAS[i][4])
    pad, gap = 20, 22
    w = (MAIN_W - 2 * pad - (n - 1) * gap) / n
    x = MAIN_X + pad + j * (w + gap)
    return x, band_y(i) + 40, w


for i, (titulo, fill, stroke, ink, cajas) in enumerate(CAPAS):
    y = band_y(i)
    out.append(f'<rect x="{MAIN_X}" y="{y}" width="{MAIN_W}" height="{BAND_H}" rx="12" '
               f'fill="{fill}" fill-opacity="0.45" stroke="{stroke}" stroke-width="1.5"/>')
    out.append(f'<text x="{MAIN_X + 16}" y="{y + 26}" font-size="16" font-weight="bold" '
               f'fill="{ink}">{escape(titulo)}</text>')
    for j, (nombre, sub) in enumerate(cajas):
        x, by, w = box_geom(i, j)
        out.append(f'<rect x="{x:.1f}" y="{by}" width="{w:.1f}" height="{BOX_H}" rx="8" '
                   f'fill="#ffffff" stroke="{stroke}" stroke-width="2"/>')
        out.append(f'<text x="{x + w/2:.1f}" y="{by + 31}" text-anchor="middle" font-size="17" '
                   f'font-weight="bold" fill="{ink}">{escape(nombre)}</text>')
        out.append(f'<text x="{x + w/2:.1f}" y="{by + 54}" text-anchor="middle" font-size="12.5" '
                   f'fill="#333">{escape(sub)}</text>')

for i, a, b, txt in FLECHAS_INTERNAS:
    xa, y, wa = box_geom(i, a)
    xb, _, _ = box_geom(i, b)
    yy = y + BOX_H / 2
    dash = ' stroke-dasharray="6 4"' if txt else ""
    out.append(f'<line x1="{xa + wa + 2:.1f}" y1="{yy}" x2="{xb - 3:.1f}" y2="{yy}" '
               f'stroke="#333" stroke-width="2"{dash} marker-end="url(#a)"/>')

for i, rel, txt, doble in FLECHAS_ENTRE:
    x = MAIN_X + MAIN_W * rel
    y1, y2 = band_y(i) + BAND_H + 2, band_y(i + 1) - 3
    start = ' marker-start="url(#a)"' if doble else ""
    out.append(f'<line x1="{x}" y1="{y1}" x2="{x}" y2="{y2}" stroke="#333" stroke-width="2.5"'
               f'{start} marker-end="url(#a)"/>')
    out.append(f'<text x="{x + 12}" y="{(y1 + y2) / 2 + 5}" font-size="14" fill="#222">'
               f'{escape(txt)}</text>')

# Carril derecho: microservicios -> datos (atraviesa por fuera la capa de mensajería)
y1 = band_y(3) + BAND_H / 2
y2 = band_y(5) + BAND_H / 2
out.append(f'<path d="M{MAIN_X + MAIN_W - 2},{y1} H{LANE_X + 20} V{y2} H{MAIN_X + MAIN_W + 2}" '
           f'fill="none" stroke="#333" stroke-width="2.5" marker-end="url(#a)"/>')
out.append(f'<text transform="translate({LANE_X + 36},{(y1 + y2) / 2}) rotate(90)" '
           f'text-anchor="middle" font-size="13" fill="#222">lee / escribe (pool)</text>')

# Barra izquierda: Terraform
ty, th = band_y(1), band_y(5) + BAND_H - band_y(1)
out.append(f'<rect x="30" y="{ty}" width="90" height="{th}" rx="12" fill="#eeeeee" '
           f'stroke="#555" stroke-width="2"/>')
out.append(f'<text transform="translate(80,{ty + th / 2}) rotate(-90)" text-anchor="middle" '
           f'font-size="18" font-weight="bold" fill="#111">Terraform (IaC) — '
           f'un módulo "region" reutilizado en 3 regiones</text>')

# Llave derecha: región x3
ry, rh = band_y(2), band_y(5) + BAND_H - band_y(2)
bx = LANE_X + 70
out.append(f'<path d="M{bx},{ry} h14 V{ry + rh} h-14" fill="none" stroke="#555" stroke-width="2"/>')
out.append(f'<text transform="translate({bx + 40},{ry + rh / 2}) rotate(90)" text-anchor="middle" '
           f'font-size="15" font-weight="bold" fill="#333">Por región ×3: sa-east-1 · us-east-1 · '
           f'eu-west-1 — 3 zonas de disponibilidad</text>')

out.append(f'<text x="{W/2}" y="{H - 18}" text-anchor="middle" font-size="13" fill="#555">'
           'Lo crítico es sincrónico (capas 1→2→3→4→6); el resto viaja por la capa 5. '
           'Aurora Global DB + MSK Replicator replican a la región secundaria (RTO ≤ 15 min).'
           '</text>')
out.append("</svg>")

with open("arquitectura.svg", "w", encoding="utf-8") as f:
    f.write("\n".join(out))
print("arquitectura.svg generado")
