# Lambda zips, named by the hash of uv.lock and the source. The deploy job uploads the
# zip before `apply`, so the bucket must exist before the stack does. Old zips stay for
# a `git revert` to redeploy them (CI/CD e IaC, «Vuelta atrás»).

resource "aws_s3_bucket" "artifacts" {
  bucket = "twochi-artifacts-${local.account_id}"
}

resource "aws_s3_bucket_ownership_controls" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id

  rule {
    id     = "old-zips"
    status = "Enabled"

    filter {}

    expiration {
      days = 180
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 7
    }
  }
}
