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
