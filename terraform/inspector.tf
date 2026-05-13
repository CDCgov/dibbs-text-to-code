#############
# Inspector v2 suppression rules
#############
# CVE-2026-3219 (pip TAR/ZIP confusion) has no upstream fix as of the review
# date below. pip ships inside the public.ecr.aws/lambda/python:3.12 base
# image but is never invoked at Lambda runtime, so the practical risk is nil.
# Scope the suppression to our three ECR repos and revisit at the review date
# in case pip publishes a fix or the base image stops shipping the affected
# version.
resource "aws_inspector2_filter" "pip_cve_2026_3219" {
  name        = "ttc-suppress-pip-cve-2026-3219"
  action      = "SUPPRESS"
  description = "pip 25.x (CVE-2026-3219): no fix available; pip is not invoked at Lambda runtime. Review by 2026-08-10."
  reason      = "Vulnerable code present in base image but not on the runtime execution path."

  filter_criteria {
    vulnerability_id {
      comparison = "EQUALS"
      value      = "CVE-2026-3219"
    }

    ecr_image_repository_name {
      comparison = "EQUALS"
      value      = aws_ecr_repository.ttc_lambda.name
    }
    ecr_image_repository_name {
      comparison = "EQUALS"
      value      = aws_ecr_repository.index_lambda.name
    }
    ecr_image_repository_name {
      comparison = "EQUALS"
      value      = aws_ecr_repository.augmentation_lambda.name
    }
  }

  tags = local.tags
}
