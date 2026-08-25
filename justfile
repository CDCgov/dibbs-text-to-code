set windows-shell := ["powershell.exe", "-c"]

alias h := _default
alias help := _default

@_default:
    just --list --list-submodules

alias b := bootstrap

[group('sub-command')]
[doc('Testing commands')]
mod test './.justscripts/just/test.just'

[doc("Initialize the development environment")]
bootstrap:
    uv sync --all-packages
    pre-commit install

[doc("Sync Python environment")]
sync:
    uv sync --all-packages

[doc("Run type checking")]
ty *ARGS:
    uv run ty check {{ARGS}}

[doc("Run Ruff check")]
ruff *ARGS:
    uv run ruff check {{ARGS}}

[doc("Run Terraform commands")]
[working-directory("terraform")]
[positional-arguments]
terraform COMMAND *ARGS:
    #!/usr/bin/env bash
    set -euo pipefail

    command="$1"
    shift

    if [[ "$command" == "plan" || "$command" == "apply" ]]; then
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

        terraform "$command" "$@" \
          -var="ttc_lambda_image_tag=${TTC_IMAGE_TAG}" \
          -var="index_lambda_image_tag=${INDEX_IMAGE_TAG}" \
          -var="augmentation_lambda_image_tag=${AUGMENTATION_IMAGE_TAG}"
    else
        terraform "$command" "$@"
    fi