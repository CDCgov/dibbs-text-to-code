# load_test_corpus.py
#
# Generates a salted eICR corpus (plus paired Schematron reports) for
# scripts/load_test.sh.
#
# Each document is templated from scripts/test_eicr.xml with a base
# nonstandard input from the test-cases JSON, then salted with a unique
# run/arm/index marker (e.g. "K+, Whole Blood [lt-3f9a2c1b-baseline-042]").
# The TTC result cache is keyed by sha256 of the lowercased candidate text,
# so a unique salt guarantees every document misses the cache and takes the
# full embedding + OpenSearch KNN path — without needing access to the
# (VPC-only) OpenSearch domain to clear anything between runs.
#
# Salts are stable across passes: pass 2 reuses pass 1's salted texts with
# fresh filenames and document UUIDs. A 2-pass run therefore measures the
# cold-cache path (pass 1) and the warm result-cache path (pass 2).
#
# Schematron reports are expensive (one Saxon transform each), but templated
# documents differ only in the salted text and document UUIDs. The generator
# validates the first document of each base case and, if none of those
# doc-specific values leak into the report XML, reuses that report for every
# other document of the same base case. If they do leak, it falls back to
# per-document validation for that base case.

import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

from validation import build_schematron_report_xml


def template_eicr(src: str, name: str) -> tuple[str, str, str]:
    """Template the source eICR with a candidate name and fresh document UUIDs.

    Mirrors bash_eicr_templater.py: rewrites the first displayName and
    originalText so the TTC pipeline has a unique text candidate to resolve,
    and stamps fresh UUIDs on <id>/<setId> so the document looks new to
    downstream systems.

    :param src: The source eICR XML text.
    :param name: The (salted) nonstandard input to inject.
    :returns: A tuple of (templated XML, document id UUID, setId UUID).
    """
    doc_id, set_id = str(uuid.uuid4()), str(uuid.uuid4())
    out = re.sub(r'displayName="[^"]*"', "displayName=" + quoteattr(name), src, count=1)
    out = re.sub(
        r"(<originalText[^>]*>)[^<]*(</originalText>)",
        lambda m: m.group(1) + escape(name) + m.group(2),
        out,
        count=1,
    )
    out = re.sub(r'<id root="[0-9a-f-]+"', f'<id root="{doc_id}"', out, count=1)
    out = re.sub(r'<setId extension="[0-9a-f-]+"', f'<setId extension="{set_id}"', out, count=1)
    return out, doc_id, set_id


def main() -> int:
    """Generate the corpus, reports, per-pass file lists, and manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", required=True, help="Path to the test-cases JSON file")
    parser.add_argument("--source-eicr", required=True, help="Path to the template eICR XML")
    parser.add_argument("--out-dir", required=True, help="Directory to write the corpus into")
    parser.add_argument("--docs", type=int, required=True, help="Documents per pass")
    parser.add_argument("--passes", type=int, default=1, help="Number of passes (default 1)")
    parser.add_argument("--run-id", required=True, help="Unique id for this load-test run")
    parser.add_argument("--arm", required=True, help="A/B arm label (e.g. baseline, branch)")
    args = parser.parse_args()

    with open(args.cases) as fp:
        cases = json.load(fp)["test_cases"]
    src = Path(args.source_eicr).read_text()

    out_dir = Path(args.out_dir)
    (out_dir / "eicrs").mkdir(parents=True, exist_ok=True)
    (out_dir / "reports").mkdir(parents=True, exist_ok=True)

    # base-case index -> reusable report XML, or None if doc-specific values
    # leak into the report and each document needs its own Saxon run.
    report_cache: dict[int, str | None] = {}
    reused = generated = 0
    manifest_docs = []

    for pass_num in range(1, args.passes + 1):
        pass_label = f"p{pass_num}"
        filenames = []
        for i in range(args.docs):
            base_idx = i % len(cases)
            case = cases[base_idx]
            # The marker (not the pass) determines the result-cache key, so
            # pass 2 repeats pass 1's texts and hits the cache pass 1 filled.
            marker = f"[lt-{args.run_id}-{args.arm}-{i:03d}]"
            salted = f"{case['nonstandard_in']} {marker}"
            filename = f"loadtest_{args.run_id}_{args.arm}_{pass_label}_{i:04d}.xml"

            doc, doc_id, set_id = template_eicr(src, salted)
            (out_dir / "eicrs" / filename).write_text(doc)

            if base_idx not in report_cache:
                report = build_schematron_report_xml(doc)
                leaks = any(v in report for v in (marker, doc_id, set_id))
                report_cache[base_idx] = None if leaks else report
                generated += 1
            else:
                cached = report_cache[base_idx]
                if cached is not None:
                    report = cached
                    reused += 1
                else:
                    report = build_schematron_report_xml(doc)
                    generated += 1
            (out_dir / "reports" / filename).write_text(report)

            filenames.append(filename)
            manifest_docs.append(
                {
                    "filename": filename,
                    "pass": pass_label,
                    "index": i,
                    "base_input": case["nonstandard_in"],
                    "salted_input": salted,
                    "expected_loinc": case["numeric_loinc_code"],
                    "expected_name": case["correct_standardized_code"],
                }
            )
            if (len(manifest_docs)) % 50 == 0:
                print(f"  templated {len(manifest_docs)} documents...", file=sys.stderr)

        (out_dir / f"files_{pass_label}.txt").write_text("\n".join(filenames) + "\n")

    manifest = {
        "run_id": args.run_id,
        "arm": args.arm,
        "docs_per_pass": args.docs,
        "passes": args.passes,
        "cases_file": str(args.cases),
        "docs": manifest_docs,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    print(
        f"  corpus: {len(manifest_docs)} documents across {args.passes} pass(es); "
        f"schematron reports: {generated} generated, {reused} reused",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
