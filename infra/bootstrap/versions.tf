# Bootstrap: what must exist before the pipeline can run. Applied once, by hand, from a
# person's machine with `aws login` (CI/CD e IaC, «Terraform: estructura, estado y arranque»).

terraform {
  required_version = "1.17.2"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "6.73.0"
    }
  }

  # Partial configuration: the bucket name carries the account id, which stays out of
  # the repository. See README.md for the first apply and the state migration.
  backend "s3" {
    key          = "bootstrap/terraform.tfstate"
    region       = "eu-west-1"
    encrypt      = true
    use_lockfile = true
  }
}

provider "aws" {
  region = "eu-west-1"

  default_tags {
    tags = {
      Project   = "twochi"
      ManagedBy = "terraform/bootstrap"
    }
  }
}

data "aws_caller_identity" "current" {}

locals {
  account_id = data.aws_caller_identity.current.account_id

  # Regions Twochi uses: the stack, CloudFront's certificate and WAF, and Guardrails.
  allowed_regions = ["eu-west-1", "us-east-1", "eu-north-1"]

  # Bucket names are global, so they end with the account id. See buckets.tf.
  state_bucket     = "twochi-tfstate-${local.account_id}"
  artifacts_bucket = "twochi-artifacts-${local.account_id}"
  backups_bucket   = "twochi-backups-${local.account_id}"
  dataset_bucket   = "twochi-dataset-${local.account_id}"
  bootstrap_buckets = [
    local.state_bucket,
    local.artifacts_bucket,
    local.backups_bucket,
    local.dataset_bucket,
  ]
}
