# twochi-apply: writes the stack, only from jobs in the `prod` environment, which waits
# for a person's approval and only runs from `main`. Writes are scoped to this account
# and to `twochi-*` names; roles it creates must carry the workload boundary; bootstrap,
# its buckets and their data are out of reach.
#
# The real control is that approval: whoever can apply can change what runs in prod.
# These denies narrow what one approved apply can do: no reaching secrets, real data or
# bootstrap, no public Function URL, no invoke or queue rights for other accounts and no
# streaming logs out. A workload role whose trust names an outside account or a broad
# OIDC subject is not something IAM can deny by content: the boundary keeps such a
# session away from secrets and data, and Access Analyzer reports the trust.
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

  bootstrap_bucket_arns = [for name in local.bootstrap_buckets : "arn:aws:s3:::${name}"]
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
      # Alarms on CloudFront and WAF metrics live in us-east-1, with their own topic.
      "arn:aws:cloudwatch:*:${local.acct}:alarm:twochi-*",
      "arn:aws:sns:*:${local.acct}:twochi-*",
      "arn:aws:events:*:${local.acct}:rule/twochi-*",
      # The account holds only Twochi, so CloudFront, WAF and ACM are scoped to it.
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
      "route53:GetChange",
    ]
    resources = ["*"]
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

  # Reads stay allowed: the stack builds on the boundary and refreshes need them.
  statement {
    sid         = "ProtectBootstrap"
    effect      = "Deny"
    not_actions = ["iam:Get*", "iam:List*"]
    resources   = local.bootstrap_iam_arns
  }

  # Detection belongs to bootstrap (TWO-19): the stack cannot switch GuardDuty off,
  # archive its findings or hand it to another account.
  statement {
    sid         = "LeaveDetectionAlone"
    effect      = "Deny"
    not_actions = ["guardduty:Get*", "guardduty:List*", "guardduty:Describe*"]
    resources   = ["*"]
  }

  # Function URLs only with AWS_IAM: the edge signs with OAC.
  statement {
    sid    = "NoPublicFunctionUrl"
    effect = "Deny"
    actions = [
      "lambda:CreateFunctionUrlConfig",
      "lambda:UpdateFunctionUrlConfig",
      "lambda:AddPermission",
    ]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "lambda:FunctionUrlAuthType"
      values   = ["NONE"]
    }
  }

  # Invoke rights go only to the AWS services of this design, never to an account.
  statement {
    sid       = "InvokeOnlyFromOwnServices"
    effect    = "Deny"
    actions   = ["lambda:AddPermission"]
    resources = ["*"]

    condition {
      test     = "StringNotEquals"
      variable = "lambda:Principal"
      values = [
        "cloudfront.amazonaws.com",
        "events.amazonaws.com",
        "scheduler.amazonaws.com",
        "sns.amazonaws.com",
      ]
    }
  }

  # Logs, queues and topics never stream to or grant another account.
  statement {
    sid    = "NoDataOutOfTheAccount"
    effect = "Deny"
    actions = [
      "logs:PutSubscriptionFilter",
      "logs:CreateExportTask",
      "logs:PutDestination",
      "logs:PutDestinationPolicy",
      "logs:CreateDelivery",
      "logs:PutDeliveryDestination",
      "logs:PutDeliveryDestinationPolicy",
      "logs:PutDeliverySource",
      "sqs:AddPermission",
      "sns:AddPermission",
    ]
    resources = ["*"]
  }

  # Alarm topics deliver by email only.
  statement {
    sid       = "EmailSubscriptionsOnly"
    effect    = "Deny"
    actions   = ["sns:Subscribe"]
    resources = ["*"]

    condition {
      test     = "StringNotEquals"
      variable = "sns:Protocol"
      values   = ["email"]
    }
  }

  # The CAA record and the delegation belong to bootstrap.
  statement {
    sid       = "KeepZonePolicy"
    effect    = "Deny"
    actions   = ["route53:ChangeResourceRecordSets"]
    resources = ["*"]

    condition {
      test     = "ForAnyValue:StringEquals"
      variable = "route53:ChangeResourceRecordSetsRecordTypes"
      values   = ["CAA", "NS", "DS"]
    }
  }

  # A workload role that trusts twochi-apply would let it step around every deny here.
  statement {
    sid       = "NeverBecomeAWorkload"
    effect    = "Deny"
    actions   = ["sts:AssumeRole", "sts:TagSession", "sts:SetSourceIdentity"]
    resources = ["arn:aws:iam::${local.acct}:role/*"]
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

  # Bootstrap's buckets keep the configuration bootstrap gives them. On them, only
  # object reads, writes and deletes (state, lock files and zips) and listing; no
  # policy, ACL, inventory, tagging or version purge.
  statement {
    sid    = "ProtectBootstrapBuckets"
    effect = "Deny"
    not_actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket",
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:PutObject",
      "s3:DeleteObject",
    ]
    resources = concat(
      local.bootstrap_bucket_arns,
      [for arn in local.bootstrap_bucket_arns : "${arn}/*"],
    )
  }

  # The stack writes its own state; bootstrap's state and the data buckets are not its
  # business.
  statement {
    sid     = "ProtectBootstrapObjects"
    effect  = "Deny"
    actions = ["s3:PutObject", "s3:DeleteObject"]
    resources = [
      "arn:aws:s3:::${local.state_bucket}/bootstrap/*",
      "arn:aws:s3:::${local.backups_bucket}/*",
      "arn:aws:s3:::${local.dataset_bucket}/*",
    ]
  }

  statement {
    sid    = "ProtectZoneAndDetection"
    effect = "Deny"
    actions = [
      "route53:DeleteHostedZone",
      "access-analyzer:DeleteAnalyzer",
      "access-analyzer:CreateArchiveRule",
      "access-analyzer:UpdateArchiveRule",
      "s3:PutAccountPublicAccessBlock",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role" "apply" {
  name                 = "twochi-apply"
  description          = "Terraform apply for the Twochi stack, from the prod environment."
  assume_role_policy   = data.aws_iam_policy_document.github_trust["apply"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "apply_read" {
  role       = aws_iam_role.apply.name
  policy_arn = aws_iam_policy.ci_read.arn
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
