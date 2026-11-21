# Permissions boundary for every role the stack creates (one per Lambda, the scheduler's).
# twochi-apply can only create roles that carry it, so a merged PR cannot hand a Lambda
# more than this ceiling. Each role still gets its own minimal policy in the stack.

data "aws_iam_policy_document" "workload_boundary" {
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["arn:aws:logs:eu-west-1:${local.account_id}:log-group:/aws/lambda/twochi-*:*"]
  }

  statement {
    sid = "Queues"
    actions = [
      "sqs:SendMessage",
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility",
      "sqs:GetQueueAttributes",
    ]
    resources = ["arn:aws:sqs:eu-west-1:${local.account_id}:twochi-*"]
  }

  statement {
    sid = "Schedules"
    actions = [
      "scheduler:CreateSchedule",
      "scheduler:UpdateSchedule",
      "scheduler:DeleteSchedule",
      "scheduler:GetSchedule",
    ]
    resources = ["arn:aws:scheduler:eu-west-1:${local.account_id}:schedule/twochi/*"]
  }

  statement {
    sid       = "PassWorkloadRoles"
    actions   = ["iam:PassRole"]
    resources = ["arn:aws:iam::${local.account_id}:role/twochi-*"]

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["scheduler.amazonaws.com"]
    }
  }

  statement {
    sid       = "InvokeWorkloads"
    actions   = ["lambda:InvokeFunction"]
    resources = ["arn:aws:lambda:eu-west-1:${local.account_id}:function:twochi-*"]
  }

  statement {
    sid       = "ReadOwnSecrets"
    actions   = ["ssm:GetParameter", "ssm:GetParameters"]
    resources = ["arn:aws:ssm:eu-west-1:${local.account_id}:parameter/twochi/prod/*"]
  }

  statement {
    sid       = "DecryptThroughSsm"
    actions   = ["kms:Decrypt"]
    resources = ["arn:aws:kms:eu-west-1:${local.account_id}:key/*"]

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.eu-west-1.amazonaws.com"]
    }
  }

  statement {
    sid       = "Objects"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["arn:aws:s3:::twochi-*/*"]
  }

  # No workload touches state, artifacts, backups or the dataset: those belong to the
  # pipeline and to people.
  statement {
    sid       = "NotBootstrapBuckets"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [for name in local.bootstrap_buckets : "arn:aws:s3:::${name}/*"]
  }

  # The Guardrails API has no resources to scope (AWS, «Conexiones y permisos»).
  statement {
    sid       = "ShadowScreening"
    actions   = ["bedrock:InvokeGuardrailChecks"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = ["eu-north-1"]
    }
  }
}

resource "aws_iam_policy" "workload_boundary" {
  name        = "twochi-workload-boundary"
  description = "Ceiling for every role the Twochi stack creates."
  policy      = data.aws_iam_policy_document.workload_boundary.json
}
