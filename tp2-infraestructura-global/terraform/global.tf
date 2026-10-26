# =============================================================================
# Capa global: DNS por latencia (Route 53) + CDN (CloudFront) + WAF
# =============================================================================

data "aws_route53_zone" "main" {
  provider = aws.us
  name     = var.domain_name
}

# Bucket de assets estáticos del checkout (JS/CSS/imágenes). Privado:
# solo CloudFront puede leerlo (Origin Access Control).
resource "aws_s3_bucket" "static" {
  provider = aws.us
  bucket   = "pagoglobal-static-${var.environment}"
}

resource "aws_s3_bucket_public_access_block" "static" {
  provider                = aws.us
  bucket                  = aws_s3_bucket.static.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_cloudfront_origin_access_control" "static" {
  provider                          = aws.us
  name                              = "pagoglobal-static-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_iam_policy_document" "static_cdn_read" {
  statement {
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.static.arn}/*"]
    principals {
      type        = "Service"
      identifiers = ["cloudfront.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "AWS:SourceArn"
      values   = [aws_cloudfront_distribution.cdn.arn]
    }
  }
}

resource "aws_s3_bucket_policy" "static" {
  provider = aws.us
  bucket   = aws_s3_bucket.static.id
  policy   = data.aws_iam_policy_document.static_cdn_read.json
}

# Certificado TLS para CloudFront (debe estar en us-east-1).
resource "aws_acm_certificate" "cdn" {
  provider                  = aws.us
  domain_name               = var.domain_name
  subject_alternative_names = ["*.${var.domain_name}"]
  validation_method         = "DNS"
}

# WAF: reglas administradas (OWASP, IPs maliciosas) + límite por IP.
resource "aws_wafv2_web_acl" "edge" {
  provider = aws.us
  name     = "pagoglobal-edge"
  scope    = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "aws-common-rules"
    priority = 1
    override_action {
      none {}
    }
    statement {
      managed_rule_group_statement {
        vendor_name = "AWS"
        name        = "AWSManagedRulesCommonRuleSet"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "common"
      sampled_requests_enabled   = true
    }
  }

  rule {
    name     = "rate-limit-por-ip"
    priority = 2
    action {
      block {}
    }
    statement {
      rate_based_statement {
        limit              = 2000 # peticiones cada 5 minutos por IP
        aggregate_key_type = "IP"
      }
    }
    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "ratelimit"
      sampled_requests_enabled   = true
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "pagoglobal-edge"
    sampled_requests_enabled   = true
  }
}

data "aws_cloudfront_cache_policy" "optimized" {
  provider = aws.us
  name     = "Managed-CachingOptimized"
}

data "aws_cloudfront_cache_policy" "disabled" {
  provider = aws.us
  name     = "Managed-CachingDisabled"
}

data "aws_cloudfront_origin_request_policy" "all_viewer" {
  provider = aws.us
  name     = "Managed-AllViewerExceptHostHeader"
}

# CDN: estático cacheado en el edge; /v1/* (API) se reenvía sin cachear
# al endpoint de API más cercano (resuelto por el registro de latencia).
resource "aws_cloudfront_distribution" "cdn" {
  provider        = aws.us
  enabled         = true
  is_ipv6_enabled = true
  aliases         = ["checkout.${var.domain_name}"]
  web_acl_id      = aws_wafv2_web_acl.edge.arn
  price_class     = "PriceClass_All" # todas las edge locations del mundo

  origin {
    origin_id                = "static-s3"
    domain_name              = aws_s3_bucket.static.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.static.id
  }

  origin {
    origin_id   = "api"
    domain_name = "api.${var.domain_name}"
    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "static-s3"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
    compress               = true
  }

  ordered_cache_behavior {
    path_pattern             = "/v1/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate.cdn.arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

# -----------------------------------------------------------------------------
# DNS con ruteo por latencia: api.pagoglobal.com apunta a la región más
# cercana que esté sana. Si una región cae, el health check la saca.
# -----------------------------------------------------------------------------
locals {
  regions = {
    us = { module = module.region_us, region = "us-east-1" }
    sa = { module = module.region_sa, region = "sa-east-1" }
    eu = { module = module.region_eu, region = "eu-west-1" }
  }
}

resource "aws_route53_health_check" "api" {
  provider          = aws.us
  for_each          = local.regions
  fqdn              = each.value.module.alb_dns_name
  port              = 443
  type              = "HTTPS"
  resource_path     = "/health"
  request_interval  = 10
  failure_threshold = 3
}

resource "aws_route53_record" "api" {
  provider        = aws.us
  for_each        = local.regions
  zone_id         = data.aws_route53_zone.main.zone_id
  name            = "api.${var.domain_name}"
  type            = "A"
  set_identifier  = each.key
  health_check_id = aws_route53_health_check.api[each.key].id

  latency_routing_policy {
    region = each.value.region
  }

  alias {
    name                   = each.value.module.alb_dns_name
    zone_id                = each.value.module.alb_zone_id
    evaluate_target_health = true
  }
}

resource "aws_route53_record" "checkout" {
  provider = aws.us
  zone_id  = data.aws_route53_zone.main.zone_id
  name     = "checkout.${var.domain_name}"
  type     = "A"

  alias {
    name                   = aws_cloudfront_distribution.cdn.domain_name
    zone_id                = aws_cloudfront_distribution.cdn.hosted_zone_id
    evaluate_target_health = false
  }
}
