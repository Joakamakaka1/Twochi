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
    plan  = "${local.github_sub_prefix}:pull_request"
    apply = "${local.github_sub_prefix}:environment:prod"
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

# Shared by both CI roles: nothing outside the three regions (GuardDuty runs in all of
# them), and nothing that reads secrets or real data. A plan runs provider code with
# whatever the PR brings, so its role must not open anything valuable.
data "aws_iam_policy_document" "ci_guardrails" {
  statement {
    sid         = "DenyOtherRegions"
    effect      = "Deny"
    not_actions = ["guardduty:*"]
    resources   = ["*"]

    condition {
      test     = "StringNotEquals"
      variable = "aws:RequestedRegion"
      values   = local.allowed_regions
    }
  }

  statement {
    sid    = "DenySecretValues"
    effect = "Deny"
    actions = [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath",
      "ssm:GetParameterHistory",
    ]
    resources = ["arn:aws:ssm:*:${local.account_id}:parameter/twochi/*"]
  }

  statement {
    sid       = "DenyDecrypt"
    effect    = "Deny"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
  }

  # With S3's default encryption, denying kms:Decrypt is not enough (AWS, «Conexiones
  # y permisos»): reading the objects is denied explicitly.
  statement {
    sid     = "DenyRealData"
    effect  = "Deny"
    actions = ["s3:GetObject", "s3:GetObjectVersion"]
    resources = [
      "arn:aws:s3:::${local.backups_bucket}/*",
      "arn:aws:s3:::${local.dataset_bucket}/*",
    ]
  }
}
