terraform {
  backend "s3" {
    bucket         = "dibbs-ttc-terraform-state"
    key            = "terraform.tfstate"
    region         = "us-east-2"
    dynamodb_table = "dibbs-ttc-terraform-lock"
    encrypt        = true
  }
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.86.0"
    }
  }
  required_version = "~> 1.14.0"
}

provider "aws" {
  region = var.region # us-east-2
  default_tags {
    tags = {
      owner       = "skylight"
      environment = "demo"
      project     = "dibbs-text-to-code"
    }
  }
}

# CloudFront only accepts ACM certificates issued in us-east-1, regardless of
# the distribution's origins' region.
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
  default_tags {
    tags = {
      owner       = "skylight"
      environment = "demo"
      project     = "dibbs-text-to-code"
    }
  }
}
