# The twochi.jcvstro.dev zone lives in Route 53, delegated from Cloudflare, where
# jcvstro.dev is. It is here and not in the stack because its name servers are copied
# by hand into Cloudflare: a recreated zone would get new ones and break the delegation.
# See docs/adr/0002-route53-subzone-delegated-from-cloudflare.md.

resource "aws_route53_zone" "twochi" {
  name    = "twochi.jcvstro.dev"
  comment = "Twochi. Delegated from the jcvstro.dev zone in Cloudflare."

  lifecycle {
    prevent_destroy = true
  }
}

# jcvstro.dev has CAA records in Cloudflare that do not name Amazon. CAA lookups stop at
# the closest name that has any, so this record lets ACM issue the CloudFront
# certificate for the subzone (https://docs.aws.amazon.com/acm/latest/userguide/setup-caa.html).
resource "aws_route53_record" "caa" {
  zone_id = aws_route53_zone.twochi.zone_id
  name    = aws_route53_zone.twochi.name
  type    = "CAA"
  ttl     = 3600
  records = [
    "0 issue \"amazon.com\"",
    "0 issue \"amazontrust.com\"",
    "0 issue \"awstrust.com\"",
    "0 issue \"amazonaws.com\"",
    "0 issuewild \";\"",
  ]
}
