set working-directory := '../..'

[doc("Run unit tests, forwarding optional arguments to pytest")]
unit *ARGS:
    uv run pytest -m "not e2e" {{ ARGS }}

[doc("Run e2e tests, forwarding optional arguments to pytest")]
e2e *ARGS:
    uv run pytest -m "e2e" {{ ARGS }}

[doc("Run all tests, forwarding optional arguments to pytest")]
all *ARGS:
    uv run pytest {{ ARGS }}

[doc("Run tests with coverage, specifying the package to measure coverage for")]
coverage *ARGS:
    uv run pytest {{ ARGS }} --cov={{ARGS}} --cov-report=term-missing