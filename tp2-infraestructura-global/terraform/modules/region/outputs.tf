output "alb_dns_name" {
  value = aws_lb.public.dns_name
}

output "alb_zone_id" {
  value = aws_lb.public.zone_id
}

output "api_gateway_endpoint" {
  value = aws_apigatewayv2_api.public.api_endpoint
}

output "ledger_writer_endpoint" {
  value = aws_rds_cluster.ledger.endpoint
}

output "redis_endpoint" {
  value = aws_elasticache_replication_group.redis.configuration_endpoint_address
}

output "kafka_bootstrap_brokers" {
  value = aws_msk_cluster.events.bootstrap_brokers_sasl_iam
}

output "webhooks_queue_url" {
  value = aws_sqs_queue.webhooks.id
}

output "webhooks_dlq_url" {
  value = aws_sqs_queue.webhooks_dlq.id
}

output "files_bucket" {
  value = aws_s3_bucket.files.bucket
}
