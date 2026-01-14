set windows-shell := ["powershell.exe", "-c"]

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
    uv sync --all-packages
    pre-commit install
    npm i --save-dev

[doc("Run tests, forwarding optional arguments to pytest")]
test *ARGS:
    uv run pytest {{ ARGS }}

[doc("Sync Python environment")]
sync:
    uv sync --all-packages

[doc("Run type checking")]
ty:
    uv run ty check

[doc("Run Ruff check")]
ruff:
    uv run ruff check
