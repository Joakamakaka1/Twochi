# What the CI roles may read: the services the stack uses, and nothing else. It replaces
# ReadOnlyAccess, which also reads the account's contact, tax, payment and billing data,
# CloudTrail events with source IPs and support cases; with public Actions logs, a PR
# step could print any of it. Object reads, secrets and payloads are denied on top of
# this in the guardrails.

data "aws_iam_policy_document" "ci_read" {
  statement {
    sid = "ReadStackServices"
    actions = [
      "access-analyzer:Get*",
      "access-analyzer:List*",
      "acm:Describe*",
      "acm:Get*",
      "acm:List*",
      "apigateway:GET",
      "budgets:Describe*",
      "budgets:ListTagsForResource",
      "budgets:ViewBudget",
      "cloudfront:Describe*",
      "cloudfront:Get*",
      "cloudfront:List*",
      "cloudwatch:Describe*",
      "cloudwatch:Get*",
      "cloudwatch:List*",
      "events:Describe*",
      "events:List*",
      "guardduty:Describe*",
      "guardduty:Get*",
      "guardduty:List*",
      "iam:Get*",
      "iam:List*",
      "lambda:Get*",
      "lambda:List*",
      "logs:Describe*",
      "logs:ListTagsForResource",
      "logs:ListTagsLogGroup",
      "route53:Get*",
      "route53:List*",
      "s3:Get*",
      "s3:List*",
      "scheduler:Get*",
      "scheduler:List*",
      "sns:Get*",
      "sns:List*",
      "sqs:Get*",
      "sqs:List*",
      "ssm:DescribeParameters",
      "ssm:ListTagsForResource",
      "tag:GetResources",
      "wafv2:Describe*",
      "wafv2:Get*",
      "wafv2:List*",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_policy" "ci_read" {
  name        = "twochi-ci-read"
  description = "Reads for terraform plan and apply on the Twochi stack, and nothing else."
  policy      = data.aws_iam_policy_document.ci_read.json
}
