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

[doc("Regenerate validation temp files and run validation tests")]
validation:
    uv run python -c "from pathlib import Path; output = Path('validation/src/validation/eicr-validator/output'); [file.unlink(missing_ok=True) for file in (output / 'stage1.sch.tmp', output / 'stage2.sch.tmp', output / 'validator.xsl.tmp', output / 'voc_ttc.xml')]"
    uv run pytest packages/validation