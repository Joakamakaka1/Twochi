output "state_bucket" {
  description = "Backend bucket for the stack: -backend-config=\"bucket=...\"."
  value       = module.state_bucket.id
}

output "artifacts_bucket" {
  description = "Bucket for the Lambda zips."
  value       = module.artifacts_bucket.id
}

output "backups_bucket" {
  description = "Bucket for the daily database dumps."
  value       = module.backups_bucket.id
}

output "dataset_bucket" {
  description = "Bucket for the golden dataset and style samples."
  value       = module.dataset_bucket.id
}

output "plan_role_arn" {
  description = "Role the PR plan job assumes. Goes to the repository secret AWS_PLAN_ROLE_ARN (ADR 0003)."
  value       = aws_iam_role.plan.arn
}

output "apply_role_arn" {
  description = "Role the prod apply job assumes. Goes to the prod environment secret AWS_APPLY_ROLE_ARN (ADR 0003)."
  value       = aws_iam_role.apply.arn
}

output "backup_role_arn" {
  description = "Role the backup jobs assume. Goes to the backup environment secret AWS_BACKUP_ROLE_ARN (ADR 0011)."
  value       = aws_iam_role.backup.arn
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
