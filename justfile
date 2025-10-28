alias h := _default
alias help := _default

@_default:
    just --list --list-submodules

[group('sub-command')]
[doc('Run dev-related docker compose commands')]
mod dev './.justscripts/just/dev.just'

alias b := bootstrap

[doc("Initialize the development environment")]
bootstrap:
    uv sync --all-packages && pre-commit install

[doc("Run tests")]
test:
    uv run pytest

[doc("Sync Python environment")]
sync:
    uv sync --all-packages

[doc("Run type checking")]
ty:
    uv run ty check

[doc("Run Ruff check")]
ruff:
    uv run ruff check