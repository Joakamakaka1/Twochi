# twochi-apply: writes the stack, only from jobs in the `prod` environment, which waits
# for a person's approval. Writes are scoped to this account and to `twochi-*` names;
# roles it creates must carry the workload boundary; bootstrap itself is out of reach.
#
# Actions are by service and the first stack apply will show what is missing: add it
# here, in its own PR, never as a wildcard on every resource.

locals {
  acct = local.account_id

  bootstrap_iam_arns = [
    aws_iam_role.plan.arn,
    "arn:aws:iam::${local.acct}:role/twochi-apply",
    aws_iam_openid_connect_provider.github.arn,
    aws_iam_policy.workload_boundary.arn,
  ]
}

data "aws_iam_policy_document" "apply_stack" {
  statement {
    sid = "StackServices"
    actions = [
      "lambda:*",
      "sqs:*",
      "scheduler:*",
      "logs:*",
      "cloudwatch:*",
      "sns:*",
      "events:*",
      "cloudfront:*",
      "wafv2:*",
      "acm:*",
      "budgets:*",
    ]
    resources = [
      "arn:aws:lambda:eu-west-1:${local.acct}:function:twochi-*",
      "arn:aws:lambda:eu-west-1:${local.acct}:event-source-mapping:*",
      "arn:aws:sqs:eu-west-1:${local.acct}:twochi-*",
      "arn:aws:scheduler:eu-west-1:${local.acct}:schedule-group/twochi",
      "arn:aws:scheduler:eu-west-1:${local.acct}:schedule/twochi/*",
      "arn:aws:logs:eu-west-1:${local.acct}:log-group:/aws/lambda/twochi-*",
      "arn:aws:logs:eu-west-1:${local.acct}:log-group:/aws/lambda/twochi-*:*",
      "arn:aws:cloudwatch:eu-west-1:${local.acct}:alarm:twochi-*",
      "arn:aws:sns:eu-west-1:${local.acct}:twochi-*",
      "arn:aws:events:*:${local.acct}:rule/twochi-*",
      "arn:aws:cloudfront::${local.acct}:*",
      "arn:aws:wafv2:us-east-1:${local.acct}:global/*",
      "arn:aws:acm:us-east-1:${local.acct}:certificate/*",
      "arn:aws:budgets::${local.acct}:budget/twochi-*",
    ]
  }

  statement {
    sid       = "StackBuckets"
    actions   = ["s3:*"]
    resources = ["arn:aws:s3:::twochi-*", "arn:aws:s3:::twochi-*/*"]
  }

  # Actions without resource-level permissions: these only work on "*".
  statement {
    sid = "CreateWithoutResource"
    actions = [
      "acm:RequestCertificate",
      "lambda:CreateEventSourceMapping",
      "guardduty:*",
      "route53:GetChange",
    ]
    resources = ["*"]
  }

  statement {
    sid       = "GuardDutyServiceRole"
    actions   = ["iam:CreateServiceLinkedRole"]
    resources = ["arn:aws:iam::${local.acct}:role/aws-service-role/guardduty.amazonaws.com/*"]

    condition {
      test     = "StringEquals"
      variable = "iam:AWSServiceName"
      values   = ["guardduty.amazonaws.com"]
    }
  }

  statement {
    sid = "OwnZoneRecords"
    actions = [
      "route53:ChangeResourceRecordSets",
      "route53:ChangeTagsForResource",
    ]
    resources = [aws_route53_zone.twochi.arn]
  }

  statement {
    sid = "WorkloadRolesWithBoundary"
    actions = [
      "iam:CreateRole",
      "iam:PutRolePermissionsBoundary",
    ]
    resources = ["arn:aws:iam::${local.acct}:role/twochi-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PermissionsBoundary"
      values   = [aws_iam_policy.workload_boundary.arn]
    }
  }

  statement {
    sid = "ManageWorkloadRoles"
    actions = [
      "iam:DeleteRole",
      "iam:UpdateRole",
      "iam:UpdateAssumeRolePolicy",
      "iam:TagRole",
      "iam:UntagRole",
      "iam:PutRolePolicy",
      "iam:DeleteRolePolicy",
      "iam:AttachRolePolicy",
      "iam:DetachRolePolicy",
    ]
    resources = ["arn:aws:iam::${local.acct}:role/twochi-*"]
  }

  statement {
    sid       = "PassWorkloadRoles"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.acct}:role/twochi-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["lambda.amazonaws.com", "scheduler.amazonaws.com"]
    }
  }

  statement {
    sid    = "ProtectBootstrap"
    effect = "Deny"
    actions = [
      "iam:*",
    ]
    resources = local.bootstrap_iam_arns
  }

  statement {
    sid    = "KeepBoundaries"
    effect = "Deny"
    actions = [
      "iam:DeleteRolePermissionsBoundary",
      "iam:CreatePolicyVersion",
      "iam:SetDefaultPolicyVersion",
    ]
    resources = [
      "arn:aws:iam::${local.acct}:role/twochi-*",
      aws_iam_policy.workload_boundary.arn,
    ]
  }

  statement {
    sid    = "ProtectStateAndZone"
    effect = "Deny"
    actions = [
      "s3:DeleteBucket",
      "s3:PutBucketPolicy",
      "s3:DeleteBucketPolicy",
      "s3:PutBucketVersioning",
      "s3:PutLifecycleConfiguration",
      "route53:DeleteHostedZone",
    ]
    resources = [aws_s3_bucket.state.arn, aws_route53_zone.twochi.arn]
  }
}

resource "aws_iam_role" "apply" {
  name                 = "twochi-apply"
  description          = "Terraform apply for the Twochi stack, from the prod environment."
  assume_role_policy   = data.aws_iam_policy_document.github_trust["apply"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "apply_read_only" {
  role       = aws_iam_role.apply.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

resource "aws_iam_role_policy" "apply_guardrails" {
  name   = "twochi-ci-guardrails"
  role   = aws_iam_role.apply.id
  policy = data.aws_iam_policy_document.ci_guardrails.json
}

resource "aws_iam_role_policy" "apply_stack" {
  name   = "twochi-apply-stack"
  role   = aws_iam_role.apply.id
  policy = data.aws_iam_policy_document.apply_stack.json
}
