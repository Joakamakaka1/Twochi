# Every long-lived bucket lives here, out of the stack: the stack is disposable and its
# apply role cannot change these buckets' configuration or read their data. Names end
# with the account id because bucket names are global.

module "state_bucket" {
  source = "../modules/private_bucket"

  # Remote state for bootstrap and the stack. It holds every resource attribute, so it
  # is sensitive and the stack never puts a secret in it (ADR 0003).
  name            = local.state_bucket
  noncurrent_days = 90
}

module "artifacts_bucket" {
  source = "../modules/private_bucket"

  # Lambda zips, named by the hash of uv.lock and the source. The deploy job uploads
  # the zip before `apply`, and old zips stay for a `git revert` to redeploy them.
  name        = local.artifacts_bucket
  versioning  = false
  expire_days = 180
}

module "backups_bucket" {
  source = "../modules/private_bucket"

  # Daily database dumps, expired after 30 days, old versions included (Datos y vectores).
  name            = local.backups_bucket
  expire_days     = 30
  noncurrent_days = 1
}

module "dataset_bucket" {
  source = "../modules/private_bucket"

  # The golden dataset and style samples: real data, never in git.
  name = local.dataset_bucket
}

# No bucket in the account can become public, whatever a later policy or ACL says. The
# apply role has no permission to undo it.
resource "aws_s3_account_public_access_block" "this" {
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# External access findings (a trust or bucket policy that opens something to another
# account) for the whole account. Free for this analyzer type.
resource "aws_accessanalyzer_analyzer" "external" {
  analyzer_name = "twochi-external-access"
  type          = "ACCOUNT"
}
