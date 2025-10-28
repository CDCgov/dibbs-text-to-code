alias h := _default
alias help := _default

@_default:
    just --list --list-submodules

[group('alias')]
[doc('Alias for `dev`')]
mod d './.justscripts/just/dev.just'

[group('sub-command')]
[doc('Run dev-related docker compose commands')]
mod dev './.justscripts/just/dev.just'

alias b := bootstrap

[doc("Initialize the development environment")]
bootstrap:
    uv sync && pre-commit install

[doc("Run tests")]
test:
    uv run pytest