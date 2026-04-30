set working-directory := '../..'

[doc("Run unit tests, forwarding optional arguments to pytest")]
unit *ARGS:
    uv run pytest -m "not e2e" {{ ARGS }}

[doc("Run benchmarks, forwarding optional arguments to pytest")]
benchmark *ARGS:
    uv run pytest --benchmark-only --override-ini="addopts=" {{ ARGS }}

[doc("Run e2e tests, forwarding optional arguments to pytest")]
e2e *ARGS:
    uv run pytest e -m "e2e" {{ ARGS }}

[doc("Run all tests, forwarding optional arguments to pytest")]
all *ARGS:
    uv run pytest {{ ARGS }}