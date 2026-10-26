output "cdn_domain" {
  description = "Dominio de la distribución CloudFront"
  value       = aws_cloudfront_distribution.cdn.domain_name
}

output "api_endpoints" {
  description = "Load Balancer de entrada por región"
  value = {
    us = module.region_us.alb_dns_name
    sa = module.region_sa.alb_dns_name
    eu = module.region_eu.alb_dns_name
  }
}

output "webhook_dlq_urls" {
  description = "Dead Letter Queues de webhooks (monitorear que estén vacías)"
  value = {
    us = module.region_us.webhooks_dlq_url
    sa = module.region_sa.webhooks_dlq_url
    eu = module.region_eu.webhooks_dlq_url
  }
}
