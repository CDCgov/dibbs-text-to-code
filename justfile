set windows-shell := ["powershell.exe", "-c"]

alias h := _default
alias help := _default

@_default:
    just --list --list-submodules

alias b := bootstrap

[group('sub-command')]
[doc('Testing commands')]
mod test './.justscripts/just/test.just'

[group('sub-command')]
[doc('Terraform commands')]
mod terraform './.justscripts/just/terraform.just'

[doc("Initialize the development environment")]
bootstrap:
    uv sync --all-packages
    pre-commit install

[doc("Sync Python environment")]
sync:
    uv sync --all-packages

[doc("Run type checking")]
ty:
    uv run ty check

[doc("Run Ruff check")]
ruff:
    uv run ruff check