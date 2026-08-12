set working-directory := "../../terraform"

[doc("Initialize Terraform")]
init:
    terraform init

[doc("Validate Terraform configuration")]
validate: init
    terraform validate

[doc("Plan Terraform changes")]
plan: (_terraform "plan")

[doc("Apply Terraform changes")]
apply: (_terraform "apply")

[private]
_terraform action: validate
    #!/usr/bin/env bash
    set -euo pipefail

    get_image_tag() {
        local image_uri

        image_uri="$(aws lambda get-function \
          --function-name "$1" \
          --query 'Code.ImageUri' \
          --output text)"

        echo "${image_uri##*:}"
    }

    TTC_IMAGE_TAG="$(get_image_tag ttc-lambda)"
    INDEX_IMAGE_TAG="$(get_image_tag ttc-index-lambda)"
    AUGMENTATION_IMAGE_TAG="$(get_image_tag ttc-augmentation-lambda)"

    terraform "{{action}}" \
      -var="ttc_lambda_image_tag=${TTC_IMAGE_TAG}" \
      -var="index_lambda_image_tag=${INDEX_IMAGE_TAG}" \
      -var="augmentation_lambda_image_tag=${AUGMENTATION_IMAGE_TAG}"