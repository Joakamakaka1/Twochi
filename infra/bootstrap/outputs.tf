output "state_bucket" {
  description = "Backend bucket for the stack: -backend-config=\"bucket=...\"."
  value       = aws_s3_bucket.state.bucket
}

output "artifacts_bucket" {
  description = "Bucket for the Lambda zips."
  value       = aws_s3_bucket.artifacts.bucket
}

output "plan_role_arn" {
  description = "Role the PR plan job assumes. Goes to the repository variable AWS_PLAN_ROLE_ARN."
  value       = aws_iam_role.plan.arn
}

output "apply_role_arn" {
  description = "Role the prod apply job assumes. Goes to the prod environment variable AWS_APPLY_ROLE_ARN."
  value       = aws_iam_role.apply.arn
}

output "workload_boundary_arn" {
  description = "Permissions boundary every stack role must carry."
  value       = aws_iam_policy.workload_boundary.arn
}

output "zone_id" {
  description = "Route 53 zone for twochi.jcvstro.dev."
  value       = aws_route53_zone.twochi.zone_id
}

output "zone_name_servers" {
  description = "NS records to create in Cloudflare under jcvstro.dev, name `twochi`."
  value       = aws_route53_zone.twochi.name_servers
}
