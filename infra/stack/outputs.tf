output "distribution_id" {
  description = "For the front deploy's index.html invalidation."
  value       = aws_cloudfront_distribution.edge.id
}

output "web_bucket" {
  description = "Where the front deploy uploads the build."
  value       = aws_s3_bucket.web.id
}

output "api_function_name" {
  description = "For the smoke test with aws lambda invoke."
  value       = aws_lambda_function.api.function_name
}
