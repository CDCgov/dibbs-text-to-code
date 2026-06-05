"""Command-line entry point for the validation package.

Used by the AWS e2e scripts to run real Schematron validation:

    python -m validation report <eicr_path>   # print NIST <Report> XML to stdout
    python -m validation check  <eicr_path>   # exit 0 if clean, 1 if errors remain
"""

import sys
from pathlib import Path

from validation import build_schematron_report_xml, validate_eicr

_USAGE = "Usage: python -m validation {report|check} <eicr_path>"
_EXPECTED_ARG_COUNT = 2


def main(argv: list[str] | None = None) -> int:
    """Run the validation CLI.

    :param argv: Argument list (defaults to ``sys.argv[1:]``).
    :return: Process exit code.
    """
    args = sys.argv[1:] if argv is None else argv
    if len(args) != _EXPECTED_ARG_COUNT or args[0] not in {"report", "check"}:
        print(_USAGE, file=sys.stderr)
        return 2

    command, eicr_path = args
    eicr = Path(eicr_path).read_text(encoding="utf-8")

    if command == "report":
        print(build_schematron_report_xml(eicr))
        return 0

    # command == "check": fail loudly if any schematron errors remain.
    results = validate_eicr(eicr)
    if results:
        print(f"{len(results)} schematron error(s) remain:", file=sys.stderr)
        for result in results:
            print(f"  - {result.error_id} @ {result.location}", file=sys.stderr)
        return 1

    print("No schematron errors.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
