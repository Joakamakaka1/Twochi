# GitHub Actions reaches AWS only through OIDC: no AWS keys in GitHub (CI/CD e IaC,
# «Seguridad del propio pipeline», rule 5).
#
# Repositories created after 15 July 2026 get an immutable subject with owner and repo
# ids. The prefix comes from:
#   gh api /repos/Joakamakaka1/Twochi/actions/oidc/customization/sub
# Ids are public; a renamed or recreated repository breaks the trust on purpose.

locals {
  github_sub_prefix = "repo:Joakamakaka1@129002508/Twochi@1466604301"
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

# Trust for one exact subject, with the audience AWS expects.
data "aws_iam_policy_document" "github_trust" {
  for_each = {
    plan   = "${local.github_sub_prefix}:pull_request"
    apply  = "${local.github_sub_prefix}:environment:prod"
    backup = "${local.github_sub_prefix}:environment:backup"
  }

  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = [each.value]
    }
  }
}

# Shared by both CI roles: nothing outside the three regions, and nothing that reads
# secrets or real data. A plan runs provider code with whatever the PR brings, and the
# repository's logs are public, so anything these roles can read may end up published.
# GuardDuty, which runs in every region, belongs to bootstrap (ADR 0006).
data "aws_iam_policy_document" "ci_guardrails" {
  statement {
    sid       = "DenyOtherRegions"
    effect    = "Deny"
    actions   = ["*"]
    resources = ["*"]

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestedRegion"
      values   = local.allowed_regions
    }
  }

  # Terraform manages no parameters (ADR 0003), so CI never needs to read one. Path
  # reads are evaluated against the path, hence every resource.
  statement {
    sid    = "DenySecretValues"
    effect = "Deny"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
      "ssm:GetParameterHistory",
      "secretsmanager:GetSecretValue",
    ]
    resources = ["*"]
  }

  # kms:Decrypt only as Lambda decrypting the environment of a twochi-* function, which
  # GetFunction does on the caller's behalf; without it the plan sees no variables and
  # always proposes to add them back. The environment never holds secrets (ADR 0005).
  # Two statements because conditions in one statement are ANDed; a missing key matches
  # both negated operators, so direct calls stay denied.
  statement {
    sid       = "DenyDecryptOutsideLambda"
    effect    = "Deny"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "StringNotEquals"
      variable = "kms:ViaService"
      values   = ["lambda.eu-west-1.amazonaws.com"]
    }
  }

  statement {
    sid       = "DenyDecryptOutsideOwnFunctions"
    effect    = "Deny"
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      test     = "StringNotLike"
      variable = "kms:EncryptionContext:aws:lambda:FunctionArn"
      values   = ["arn:aws:lambda:eu-west-1:${local.account_id}:function:twochi-*"]
    }
  }

  # Objects are readable only in the state bucket (a plan needs it) and the artifacts
  # bucket (Lambda deploys need it). Any other bucket, today or tomorrow, stays closed.
  statement {
    sid    = "DenyObjectsOutsideStateAndArtifacts"
    effect = "Deny"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:GetObjectAttributes",
      "s3:GetObjectTorrent",
    ]
    not_resources = [
      "arn:aws:s3:::${local.state_bucket}/*",
      "arn:aws:s3:::${local.artifacts_bucket}/*",
    ]
  }

  # Bootstrap's state holds the alerts email in plain text, and the stack never reads it.
  statement {
    sid    = "DenyBootstrapState"
    effect = "Deny"
    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
      "s3:GetObjectAttributes",
      "s3:GetObjectTorrent",
    ]
    resources = ["arn:aws:s3:::${local.state_bucket}/bootstrap/*"]
  }

  # Who receives the security alerts, and the subscription ARN that would let anyone
  # unsubscribe an unauthenticated subscription, stay out of public logs.
  statement {
    sid    = "DenyAlertSubscribers"
    effect = "Deny"
    actions = [
      "sns:ListSubscriptionsByTopic",
      "sns:GetSubscriptionAttributes",
    ]
    resources = [
      local.security_alerts_topic_arn,
      "${local.security_alerts_topic_arn}:*",
    ]
  }

  # ListSubscriptions has no resource to scope; the stack's Terraform never calls it.
  statement {
    sid       = "DenyListingSubscriptions"
    effect    = "Deny"
    actions   = ["sns:ListSubscriptions"]
    resources = ["*"]
  }

  # Log lines and queue messages may carry payloads; Terraform never reads them.
  statement {
    sid    = "DenyPayloads"
    effect = "Deny"
    actions = [
      "logs:GetLogEvents",
      "logs:FilterLogEvents",
      "logs:GetLogRecord",
      "logs:GetQueryResults",
      "logs:StartQuery",
      "logs:StartLiveTail",
      "logs:Unmask",
      "logs:ListAnomalies",
      "sqs:ReceiveMessage",
      "iam:GetCredentialReport",
    ]
    resources = ["*"]
  }

  # Even the key names of real data stay private.
  statement {
    sid     = "DenyListingRealData"
    effect  = "Deny"
    actions = ["s3:ListBucket", "s3:ListBucketVersions"]
    resources = [
      "arn:aws:s3:::${local.backups_bucket}",
      "arn:aws:s3:::${local.dataset_bucket}",
    ]
  }
}
