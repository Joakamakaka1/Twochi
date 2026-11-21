# twochi-plan: reads the stack's services only (ci_read.tf), for `terraform plan -lock=false` on pull requests opened from
# branches of this repository. Fork PRs never get an OIDC token for it.

resource "aws_iam_role" "plan" {
  name                 = "twochi-plan"
  description          = "Read-only terraform plan for Twochi pull requests."
  assume_role_policy   = data.aws_iam_policy_document.github_trust["plan"].json
  max_session_duration = 3600
}

resource "aws_iam_role_policy_attachment" "plan_read" {
  role       = aws_iam_role.plan.name
  policy_arn = aws_iam_policy.ci_read.arn
}

resource "aws_iam_role_policy" "plan_guardrails" {
  name   = "twochi-ci-guardrails"
  role   = aws_iam_role.plan.id
  policy = data.aws_iam_policy_document.ci_guardrails.json
}
