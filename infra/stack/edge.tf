# The edge: one domain, CloudFront with WAF, `/api/*` to the api Lambda through OAC and
# the rest to the front bucket through OAC (AWS, «Borde: CloudFront, WAF y la entrada a
# la API»). The flat-rate Free plan allows only AWS managed cache and origin request
# policies, so no custom one is declared here.

# --- Certificate, in us-east-1 as CloudFront requires.

resource "aws_acm_certificate" "edge" {
  region            = "us-east-1"
  domain_name       = local.domain
  validation_method = "DNS"

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "certificate_validation" {
  for_each = {
    for option in aws_acm_certificate.edge.domain_validation_options :
    option.domain_name => option
  }

  zone_id         = data.aws_route53_zone.twochi.zone_id
  name            = each.value.resource_record_name
  type            = each.value.resource_record_type
  records         = [each.value.resource_record_value]
  ttl             = 300
  allow_overwrite = true
}

resource "aws_acm_certificate_validation" "edge" {
  region                  = "us-east-1"
  certificate_arn         = aws_acm_certificate.edge.arn
  validation_record_fqdns = [for record in aws_route53_record.certificate_validation : record.fqdn]
}

# --- WAF: country filter and a rate limit per IP. Not an access control: the JWT is.

resource "aws_wafv2_web_acl" "edge" {
  region = "us-east-1"
  name   = "twochi-edge"
  scope  = "CLOUDFRONT"

  default_action {
    allow {}
  }

  rule {
    name     = "only-allowed-countries"
    priority = 0

    action {
      block {}
    }

    statement {
      not_statement {
        statement {
          geo_match_statement {
            country_codes = var.allowed_countries
          }
        }
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "twochi-edge-countries"
      sampled_requests_enabled   = false
    }
  }

  rule {
    name     = "rate-per-ip"
    priority = 1

    action {
      block {}
    }

    statement {
      rate_based_statement {
        limit                 = var.requests_per_ip_per_5_minutes
        evaluation_window_sec = 300
        aggregate_key_type    = "IP"
      }
    }

    visibility_config {
      cloudwatch_metrics_enabled = true
      metric_name                = "twochi-edge-rate"
      sampled_requests_enabled   = false
    }
  }

  visibility_config {
    cloudwatch_metrics_enabled = true
    metric_name                = "twochi-edge"
    sampled_requests_enabled   = false
  }
}

# --- Origin access control: CloudFront signs every origin request with SigV4.

resource "aws_cloudfront_origin_access_control" "api" {
  name                              = "twochi-api"
  description                       = "CloudFront to the api Function URL."
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

resource "aws_cloudfront_origin_access_control" "web" {
  name                              = "twochi-web"
  description                       = "CloudFront to the front bucket."
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "disabled" {
  name = "Managed-CachingDisabled"
}

data "aws_cloudfront_cache_policy" "optimized" {
  name = "Managed-CachingOptimized"
}

# Forwards every viewer header but Host, so x-amz-content-sha256 and X-Twochi-Auth reach
# the Function URL, whose own host the signature needs. This is what Cronista proved.
data "aws_cloudfront_origin_request_policy" "all_viewer_except_host" {
  name = "Managed-AllViewerExceptHostHeader"
}

locals {
  # The Function URL is https://<id>.lambda-url.<region>.on.aws/; CloudFront wants the host.
  api_origin_host = trimsuffix(trimprefix(aws_lambda_function_url.api.function_url, "https://"), "/")
}

resource "aws_cloudfront_distribution" "edge" {
  enabled             = true
  comment             = "Twochi"
  aliases             = [local.domain]
  default_root_object = "index.html"
  http_version        = "http2and3"
  is_ipv6_enabled     = true
  price_class         = "PriceClass_100"
  web_acl_id          = aws_wafv2_web_acl.edge.arn

  origin {
    origin_id                = "web"
    domain_name              = aws_s3_bucket.web.bucket_regional_domain_name
    origin_access_control_id = aws_cloudfront_origin_access_control.web.id
  }

  origin {
    origin_id                = "api"
    domain_name              = local.api_origin_host
    origin_access_control_id = aws_cloudfront_origin_access_control.api.id

    custom_origin_config {
      http_port              = 80
      https_port             = 443
      origin_protocol_policy = "https-only"
      origin_ssl_protocols   = ["TLSv1.2"]
    }
  }

  default_cache_behavior {
    target_origin_id       = "web"
    viewer_protocol_policy = "redirect-to-https"
    allowed_methods        = ["GET", "HEAD", "OPTIONS"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.optimized.id
  }

  ordered_cache_behavior {
    path_pattern             = "/api/*"
    target_origin_id         = "api"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.disabled.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host.id
  }

  restrictions {
    # The country filter is the WAF rule above, which the flat-rate plan includes.
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    acm_certificate_arn      = aws_acm_certificate_validation.edge.certificate_arn
    ssl_support_method       = "sni-only"
    minimum_protocol_version = "TLSv1.2_2021"
  }
}

resource "aws_route53_record" "edge" {
  for_each = toset(["A", "AAAA"])

  zone_id = data.aws_route53_zone.twochi.zone_id
  name    = local.domain
  type    = each.value

  alias {
    name                   = aws_cloudfront_distribution.edge.domain_name
    zone_id                = aws_cloudfront_distribution.edge.hosted_zone_id
    evaluate_target_health = false
  }
}
