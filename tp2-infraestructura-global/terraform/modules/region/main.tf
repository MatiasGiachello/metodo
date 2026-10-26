# =============================================================================
# Módulo "region": todo lo que necesita UNA región de PagoGlobal.
# Se instancia 3 veces (us-east-1, sa-east-1, eu-west-1) desde ../../main.tf
# =============================================================================

terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  azs = slice(data.aws_availability_zones.available.names, 0, 3) # 3 AZ
}

# -----------------------------------------------------------------------------
# Red: VPC con subredes públicas (solo el Load Balancer), privadas (app)
# y de base de datos (aisladas). Nada de la app tiene IP pública.
# -----------------------------------------------------------------------------
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.13"

  name = var.name
  cidr = var.vpc_cidr
  azs  = local.azs

  public_subnets   = [for i in range(3) : cidrsubnet(var.vpc_cidr, 8, i)]
  private_subnets  = [for i in range(3) : cidrsubnet(var.vpc_cidr, 4, i + 1)]
  database_subnets = [for i in range(3) : cidrsubnet(var.vpc_cidr, 8, i + 100)]

  enable_nat_gateway     = true
  one_nat_gateway_per_az = true # sin punto único de falla

  create_database_subnet_group = true
}

# -----------------------------------------------------------------------------
# Kubernetes (EKS): corre los microservicios. El autoscaling va de
# eks_min_nodes a eks_max_nodes; los pods hacen Graceful Shutdown al bajar.
# -----------------------------------------------------------------------------
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.24"

  cluster_name    = var.name
  cluster_version = "1.31"
  vpc_id          = module.vpc.vpc_id
  subnet_ids      = module.vpc.private_subnets

  eks_managed_node_groups = {
    app = {
      instance_types = ["m6i.xlarge"]
      min_size       = var.eks_min_nodes
      desired_size   = var.eks_min_nodes
      max_size       = var.eks_max_nodes
    }
  }
}

# -----------------------------------------------------------------------------
# Security groups: cada capa solo acepta tráfico de la capa anterior.
# -----------------------------------------------------------------------------
resource "aws_security_group" "alb" {
  name   = "${var.name}-alb"
  vpc_id = module.vpc.vpc_id

  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
  }
}

resource "aws_security_group" "data" {
  name   = "${var.name}-data"
  vpc_id = module.vpc.vpc_id

  ingress {
    description     = "PostgreSQL (via PgBouncer), Redis y Kafka solo desde los nodos de EKS"
    from_port       = 0
    to_port         = 65535
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
}

# -----------------------------------------------------------------------------
# Base de datos del ledger: Aurora PostgreSQL, 1 escritor + 2 lectores en 3 AZ.
# Cifrada, con backups y protección contra borrado.
# -----------------------------------------------------------------------------
resource "aws_rds_cluster" "ledger" {
  cluster_identifier          = "${var.name}-ledger"
  engine                      = "aurora-postgresql"
  engine_version              = "16.4"
  database_name               = "ledger"
  master_username             = "pagoglobal_admin"
  manage_master_user_password = true # el secreto vive en Secrets Manager, rotado
  db_subnet_group_name        = module.vpc.database_subnet_group_name
  vpc_security_group_ids      = [aws_security_group.data.id]
  storage_encrypted           = true
  backup_retention_period     = 35
  deletion_protection         = true
  copy_tags_to_snapshot       = true
}

resource "aws_rds_cluster_instance" "ledger" {
  count              = 3 # índice 0 = escritor, 1 y 2 = lectores
  identifier         = "${var.name}-ledger-${count.index}"
  cluster_identifier = aws_rds_cluster.ledger.id
  instance_class     = "db.r6g.2xlarge"
  engine             = aws_rds_cluster.ledger.engine
}

# -----------------------------------------------------------------------------
# Redis (ElastiCache): idempotencia, rate limiting, sesiones, caché y pub/sub.
# Modo clúster, réplicas en 3 AZ y failover automático.
# -----------------------------------------------------------------------------
resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.name}-redis"
  subnet_ids = module.vpc.database_subnets
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${var.name}-redis"
  description                = "Cache, sesiones, idempotencia y rate limit"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.r6g.large"
  num_node_groups            = 3 # shards
  replicas_per_node_group    = 1
  automatic_failover_enabled = true
  multi_az_enabled           = true
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.data.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
}

# -----------------------------------------------------------------------------
# Kafka (Amazon MSK): tópico payments.events y sus consumidores.
# 3 brokers (uno por AZ), cifrado en tránsito y autenticación IAM.
# -----------------------------------------------------------------------------
resource "aws_msk_cluster" "events" {
  cluster_name           = "${var.name}-events"
  kafka_version          = "3.7.x"
  number_of_broker_nodes = 3

  broker_node_group_info {
    instance_type   = "kafka.m5.large"
    client_subnets  = module.vpc.private_subnets
    security_groups = [aws_security_group.data.id]
    storage_info {
      ebs_storage_info { volume_size = 500 }
    }
  }

  encryption_info {
    encryption_in_transit {
      client_broker = "TLS"
      in_cluster    = true
    }
  }

  client_authentication {
    sasl { iam = true }
  }

  configuration_info {
    arn      = aws_msk_configuration.events.arn
    revision = aws_msk_configuration.events.latest_revision
  }
}

resource "aws_msk_configuration" "events" {
  name           = "${var.name}-events-config"
  kafka_versions = ["3.7.x"]

  # Durabilidad: un mensaje se confirma cuando está en al menos 2 réplicas.
  server_properties = <<-EOT
    default.replication.factor=3
    min.insync.replicas=2
    num.partitions=48
    auto.create.topics.enable=false
    log.retention.hours=168
  EOT
}

# -----------------------------------------------------------------------------
# Cola de webhooks + Dead Letter Queue.
# Tras 8 intentos fallidos el mensaje pasa a la DLQ (se guarda 14 días).
# -----------------------------------------------------------------------------
resource "aws_sqs_queue" "webhooks_dlq" {
  name                      = "${var.name}-webhooks-dlq"
  message_retention_seconds = 1209600 # 14 días
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "webhooks" {
  name                       = "${var.name}-webhooks"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 345600 # 4 días
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.webhooks_dlq.arn
    maxReceiveCount     = 8
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "webhooks_dlq" {
  queue_url = aws_sqs_queue.webhooks_dlq.id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.webhooks.arn]
  })
}

# Alarma: cualquier mensaje en la DLQ debe ser investigado.
resource "aws_cloudwatch_metric_alarm" "dlq_not_empty" {
  alarm_name          = "${var.name}-webhooks-dlq-con-mensajes"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.webhooks_dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
}

# -----------------------------------------------------------------------------
# S3 de archivos (reportes de liquidación, evidencia de contracargos).
# Privado y cifrado: el acceso es solo con Presigned URLs.
# -----------------------------------------------------------------------------
resource "aws_s3_bucket" "files" {
  bucket = "${var.name}-files-${var.environment}"
}

resource "aws_s3_bucket_public_access_block" "files" {
  bucket                  = aws_s3_bucket.files.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    apply_server_side_encryption_by_default { sse_algorithm = "aws:kms" }
  }
}

resource "aws_s3_bucket_versioning" "files" {
  bucket = aws_s3_bucket.files.id
  versioning_configuration { status = "Enabled" }
}

resource "aws_s3_bucket_lifecycle_configuration" "files" {
  bucket = aws_s3_bucket.files.id
  rule {
    id     = "reportes-a-glacier"
    status = "Enabled"
    filter { prefix = "reportes/" }
    transition {
      days          = 90
      storage_class = "GLACIER"
    }
  }
}

# -----------------------------------------------------------------------------
# Entrada regional: Application Load Balancer (proxy inverso L7, TLS).
# Reparte tráfico entre las réplicas del API Gateway / Ingress del clúster.
# -----------------------------------------------------------------------------
resource "aws_lb" "public" {
  name                       = "${var.name}-alb"
  load_balancer_type         = "application"
  subnets                    = module.vpc.public_subnets
  security_groups            = [aws_security_group.alb.id]
  idle_timeout               = 3600 # conexiones WebSocket de larga duración
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "gateway" {
  name        = "${var.name}-gw"
  port        = 8080
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = module.vpc.vpc_id

  # Con Graceful Shutdown: el LB espera 30 s a que terminen las peticiones
  # en curso de un pod antes de quitarlo del todo (connection draining).
  deregistration_delay = 30

  health_check {
    path                = "/ready"
    interval            = 10
    healthy_threshold   = 2
    unhealthy_threshold = 2
  }
}

resource "aws_acm_certificate" "api" {
  domain_name       = "api.pagoglobal.com"
  validation_method = "DNS"
}

resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.public.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate.api.arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.gateway.arn
  }
}

# -----------------------------------------------------------------------------
# API Gateway (HTTP API) para la API pública de partners: valida JWT emitidos
# por el servidor OAuth 2.0, aplica cuotas y rutea por path.
# -----------------------------------------------------------------------------
resource "aws_apigatewayv2_api" "public" {
  name          = "${var.name}-api"
  protocol_type = "HTTP"
}

resource "aws_apigatewayv2_authorizer" "jwt" {
  api_id           = aws_apigatewayv2_api.public.id
  name             = "oauth-jwt"
  authorizer_type  = "JWT"
  identity_sources = ["$request.header.Authorization"]

  jwt_configuration {
    issuer   = var.jwt_issuer
    audience = var.jwt_audience
  }
}

resource "aws_apigatewayv2_vpc_link" "internal" {
  name               = "${var.name}-vpclink"
  subnet_ids         = module.vpc.private_subnets
  security_group_ids = [aws_security_group.alb.id]
}

resource "aws_lb" "internal" {
  name               = "${var.name}-nlb-int"
  internal           = true
  load_balancer_type = "network"
  subnets            = module.vpc.private_subnets
}

resource "aws_lb_listener" "internal" {
  load_balancer_arn = aws_lb.internal.arn
  port              = 80
  protocol          = "TCP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.internal.arn
  }
}

resource "aws_lb_target_group" "internal" {
  name                 = "${var.name}-int"
  port                 = 8080
  protocol             = "TCP"
  target_type          = "ip"
  vpc_id               = module.vpc.vpc_id
  deregistration_delay = 30
}

resource "aws_apigatewayv2_integration" "services" {
  api_id             = aws_apigatewayv2_api.public.id
  integration_type   = "HTTP_PROXY"
  integration_method = "ANY"
  integration_uri    = aws_lb_listener.internal.arn
  connection_type    = "VPC_LINK"
  connection_id      = aws_apigatewayv2_vpc_link.internal.id
}

# Una ruta por microservicio; todas exigen JWT con el scope adecuado.
locals {
  routes = {
    "POST /v1/payments"         = ["payments:write"]
    "GET /v1/payments/{id}"     = ["payments:read"]
    "POST /v1/refunds"          = ["payments:write"]
    "GET /v1/reports/{proxy+}"  = ["reports:read"]
    "POST /v1/files/upload-url" = ["files:write"]
  }
}

resource "aws_apigatewayv2_route" "routes" {
  for_each             = local.routes
  api_id               = aws_apigatewayv2_api.public.id
  route_key            = each.key
  target               = "integrations/${aws_apigatewayv2_integration.services.id}"
  authorization_type   = "JWT"
  authorizer_id        = aws_apigatewayv2_authorizer.jwt.id
  authorization_scopes = each.value
}

resource "aws_apigatewayv2_stage" "prod" {
  api_id      = aws_apigatewayv2_api.public.id
  name        = "$default"
  auto_deploy = true

  # Rate limiting a nivel Gateway (además del límite por comercio en Redis).
  default_route_settings {
    throttling_rate_limit  = 5000
    throttling_burst_limit = 10000
  }
}
