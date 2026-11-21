# Account threat detection and its email alerts. GuardDuty runs in every enabled region,
# because misuse tends to happen in the regions nobody watches; its findings and Access
# Analyzer's reach one topic in eu-west-1. It lives here and not in the stack so that an
# approved stack apply cannot switch it off, and because the CI roles are confined to
# three regions (ADR 0006).
#
# A finding's path: the default bus of its region, a forwarding rule, the default bus of
# eu-west-1, a central rule, the topic, the email. Cross-region targets must be event
# buses, so the topic cannot be the target of a rule in another region.

data "aws_regions" "enabled" {}

locals {
  home_region       = "eu-west-1"
  detection_regions = toset(data.aws_regions.enabled.names)
  forward_regions   = setsubtract(local.detection_regions, [local.home_region])
  home_bus_arn      = "arn:aws:events:${local.home_region}:${local.account_id}:event-bus/default"

  guardduty_forward_rule = "twochi-guardduty-forward"

  # What GuardDuty looks at here (AWS, «GuardDuty»): management events, S3 data events
  # and the Lambdas' network activity. The rest has nothing to watch in this account and
  # is switched off so that the configuration says what runs. A new detector turns every
  # optional plan on except Runtime Monitoring, so each one is declared.
  guardduty_features = {
    S3_DATA_EVENTS         = { status = "ENABLED", additional = [] }
    LAMBDA_NETWORK_LOGS    = { status = "ENABLED", additional = [] }
    EKS_AUDIT_LOGS         = { status = "DISABLED", additional = [] }
    EBS_MALWARE_PROTECTION = { status = "DISABLED", additional = [] }
    RDS_LOGIN_EVENTS       = { status = "DISABLED", additional = [] }
    RUNTIME_MONITORING = {
      status     = "DISABLED"
      additional = ["EKS_ADDON_MANAGEMENT", "ECS_FARGATE_AGENT_MANAGEMENT", "EC2_AGENT_MANAGEMENT"]
    }
  }

  guardduty_region_features = {
    for pair in setproduct(local.detection_regions, keys(local.guardduty_features)) :
    "${pair[0]}/${pair[1]}" => { region = pair[0], name = pair[1] }
  }
}

resource "aws_guardduty_detector" "this" {
  for_each = local.detection_regions

  region                       = each.key
  enable                       = true
  finding_publishing_frequency = "SIX_HOURS"
}

resource "aws_guardduty_detector_feature" "this" {
  for_each = local.guardduty_region_features

  region      = each.value.region
  detector_id = aws_guardduty_detector.this[each.value.region].id
  name        = each.value.name
  status      = local.guardduty_features[each.value.name].status

  dynamic "additional_configuration" {
    for_each = local.guardduty_features[each.value.name].additional

    content {
      name   = additional_configuration.value
      status = "DISABLED"
    }
  }
}

# The topic carries no customer data: findings describe the account. The AWS managed key
# for SNS does not let EventBridge publish, and a customer key would cost more than the
# rest of this file to protect what ends up in a plain email anyway.
resource "aws_sns_topic" "security_alerts" {
  name = "twochi-security-alerts"
}

resource "aws_sns_topic_subscription" "security_alerts_email" {
  topic_arn = aws_sns_topic.security_alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}

# Only the two central rules publish. People with IAM rights in the account manage the
# topic through their own policies; a topic policy is not needed for that.
data "aws_iam_policy_document" "security_alerts_topic" {
  statement {
    sid       = "CentralRulesPublish"
    actions   = ["sns:Publish"]
    resources = [aws_sns_topic.security_alerts.arn]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values = [
        aws_cloudwatch_event_rule.guardduty_findings.arn,
        aws_cloudwatch_event_rule.access_analyzer_findings.arn,
      ]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }
  }
}

resource "aws_sns_topic_policy" "security_alerts" {
  arn    = aws_sns_topic.security_alerts.arn
  policy = data.aws_iam_policy_document.security_alerts_topic.json
}

# Every severity: root credential use, the finding that matters most here, is Low.
# Forwarded events keep their source and region, so this rule sees every region's.
resource "aws_cloudwatch_event_rule" "guardduty_findings" {
  name        = "twochi-guardduty-findings"
  description = "GuardDuty findings from every region to the security alerts topic."
  event_pattern = jsonencode({
    source        = ["aws.guardduty"]
    "detail-type" = ["GuardDuty Finding"]
  })
}

resource "aws_cloudwatch_event_target" "guardduty_findings" {
  rule      = aws_cloudwatch_event_rule.guardduty_findings.name
  target_id = "security-alerts"
  arn       = aws_sns_topic.security_alerts.arn
}

# The analyzer lives in eu-west-1 and also covers the global IAM roles. Only active
# findings: a resolved or archived one needs no email.
resource "aws_cloudwatch_event_rule" "access_analyzer_findings" {
  name        = "twochi-access-analyzer-findings"
  description = "Active Access Analyzer findings to the security alerts topic."
  event_pattern = jsonencode({
    source        = ["aws.access-analyzer"]
    "detail-type" = ["Access Analyzer Finding"]
    detail        = { status = ["ACTIVE"] }
  })
}

resource "aws_cloudwatch_event_target" "access_analyzer_findings" {
  rule      = aws_cloudwatch_event_rule.access_analyzer_findings.name
  target_id = "security-alerts"
  arn       = aws_sns_topic.security_alerts.arn
}

# EventBridge needs a role to put events on a bus in another region.
data "aws_iam_policy_document" "findings_forwarder_trust" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["events.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [local.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      values   = ["arn:aws:events:*:${local.account_id}:rule/${local.guardduty_forward_rule}"]
    }
  }
}

data "aws_iam_policy_document" "findings_forwarder" {
  statement {
    actions   = ["events:PutEvents"]
    resources = [local.home_bus_arn]
  }
}

resource "aws_iam_role" "findings_forwarder" {
  name                 = "twochi-findings-forwarder"
  description          = "EventBridge forwards GuardDuty findings to the eu-west-1 default bus."
  assume_role_policy   = data.aws_iam_policy_document.findings_forwarder_trust.json
  max_session_duration = 3600
}

resource "aws_iam_role_policy" "findings_forwarder" {
  name   = "twochi-findings-forwarder"
  role   = aws_iam_role.findings_forwarder.id
  policy = data.aws_iam_policy_document.findings_forwarder.json
}

resource "aws_cloudwatch_event_rule" "guardduty_forward" {
  for_each = local.forward_regions

  region      = each.key
  name        = local.guardduty_forward_rule
  description = "GuardDuty findings of this region to the eu-west-1 default bus."
  event_pattern = jsonencode({
    source        = ["aws.guardduty"]
    "detail-type" = ["GuardDuty Finding"]
  })
}

resource "aws_cloudwatch_event_target" "guardduty_forward" {
  for_each = local.forward_regions

  region    = each.key
  rule      = aws_cloudwatch_event_rule.guardduty_forward[each.key].name
  target_id = "home-bus"
  arn       = local.home_bus_arn
  role_arn  = aws_iam_role.findings_forwarder.arn
}
