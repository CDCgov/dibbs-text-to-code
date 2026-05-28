"""Emit a single self-contained HTML report from `outputs/metrics.json` and `outputs/knn_top1.json`.

Plotly is embedded inline so the file can be emailed / shared without an internet
connection.
"""

from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

OUTPUTS = Path(__file__).parent / "outputs"
REFERENCE_ENV = "azure_gpu"


def load_inputs() -> tuple[dict, dict | None]:
    metrics = json.loads((OUTPUTS / "metrics.json").read_text())
    knn_path = OUTPUTS / "knn_top1.json"
    knn = json.loads(knn_path.read_text()) if knn_path.exists() else None
    return metrics, knn


def pair_summary_table(metrics: dict) -> str:
    rows = []
    for pair_key, pair in metrics["pair_metrics"].items():
        a, b = pair["envs"]
        cos = pair["cosine"]
        l2 = pair["l2"]
        max_abs = pair["max_abs_diff"]
        rows.append(
            {
                "env A": a,
                "env B": b,
                "1 - cosine min": f"{1 - cos['min']:.3e}",
                "1 - cosine mean": f"{1 - cos['mean']:.3e}",
                "L2 mean": f"{l2['mean']:.3e}",
                "L2 max": f"{l2['max']:.3e}",
                "max |Δ| mean": f"{max_abs['mean']:.3e}",
                "max |Δ| max": f"{max_abs['max']:.3e}",
            }
        )
    df = pd.DataFrame(rows).sort_values("1 - cosine mean")
    return df.to_html(index=False, classes="summary", border=0)


def cosine_to_reference_histogram(metrics: dict) -> str:
    """Plot (1 - cosine) per pair on a log x-axis.

    Cosine similarities are typically >0.99999 for this model, so (1 - cosine)
    on a log scale is the only way to see the structure of the differences.
    The reference env (azure_gpu) is preferred but if it's missing we fall
    back to all pairs.
    """
    fig = go.Figure()
    envs = metrics["envs"]
    has_reference = REFERENCE_ENV in envs

    for pair_key, pair in metrics["pair_metrics"].items():
        if has_reference and REFERENCE_ENV not in pair["envs"]:
            continue
        a, b = pair["envs"]
        label = (
            f"{[e for e in pair['envs'] if e != REFERENCE_ENV][0]} vs {REFERENCE_ENV}"
            if has_reference
            else f"{a} ↔ {b}"
        )
        cos = pair["per_description"]["cosine"]
        # Clip to epsilon so we can take log10 even when cosine == 1.0 exactly.
        one_minus = [max(1.0 - c, 1e-15) for c in cos]
        fig.add_trace(
            go.Histogram(
                x=one_minus,
                name=label,
                opacity=0.55,
                nbinsx=60,
            )
        )

    title_suffix = (
        f"to {REFERENCE_ENV}"
        if has_reference
        else "(all pairs — azure_gpu reference not yet available)"
    )
    fig.update_layout(
        barmode="overlay",
        title=f"Per-description (1 − cosine similarity) {title_suffix}",
        xaxis_title="1 − cosine similarity (log scale)",
        xaxis_type="log",
        yaxis_title="number of descriptions",
        height=420,
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def l2_histogram(metrics: dict) -> str:
    fig = go.Figure()
    for pair_key, pair in metrics["pair_metrics"].items():
        a, b = pair["envs"]
        fig.add_trace(
            go.Histogram(
                x=pair["per_description"]["l2"],
                name=f"{a} ↔ {b}",
                opacity=0.45,
                nbinsx=50,
            )
        )
    fig.update_layout(
        barmode="overlay",
        title="Per-description L2 distance (all env pairs)",
        xaxis_title="L2 distance",
        yaxis_title="number of descriptions",
        height=420,
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def outlier_table(metrics: dict) -> str:
    rows = [
        {
            "rank": i + 1,
            "description": o["description"],
            "mean variance across envs": f"{o['mean_variance_across_envs']:.6e}",
        }
        for i, o in enumerate(metrics["outliers"])
    ]
    return pd.DataFrame(rows).to_html(index=False, classes="outliers", border=0)


def knn_heatmap(knn: dict) -> str:
    envs = knn["envs"]
    matrix = knn["agreement_matrix"]
    z = [[matrix[a][b] for b in envs] for a in envs]
    text = [[f"{matrix[a][b]:.1%}" for b in envs] for a in envs]
    mode = knn.get("mode", "opensearch")
    if mode == "offline":
        title_suffix = (
            f"(offline proxy: in-memory KNN against the {knn.get('corpus_env', '?')} "
            "vectors over this 500-row subset)"
        )
    else:
        title_suffix = "(KNN against prod OpenSearch index)"

    fig = go.Figure(
        data=go.Heatmap(
            z=z,
            x=envs,
            y=envs,
            text=text,
            texttemplate="%{text}",
            colorscale="Viridis",
            zmin=0.0,
            zmax=1.0,
            colorbar={"title": "agreement"},
        )
    )
    fig.update_layout(
        title=f"Top-1 nearest-neighbor agreement across env pairs<br>{title_suffix}",
        height=480,
    )
    return fig.to_html(full_html=False, include_plotlyjs=False)


def exec_summary(metrics: dict, knn: dict | None) -> str:
    worst_cos_pair = None
    worst_cos = 1.0
    worst_l2 = 0.0
    worst_l2_pair = None
    for pair in metrics["pair_metrics"].values():
        if pair["cosine"]["min"] < worst_cos:
            worst_cos = pair["cosine"]["min"]
            worst_cos_pair = pair["envs"]
        if pair["l2"]["max"] > worst_l2:
            worst_l2 = pair["l2"]["max"]
            worst_l2_pair = pair["envs"]

    envs_list = ", ".join(metrics["envs"])
    summary_pieces = [
        f"<strong>{metrics['n_descriptions']}</strong> descriptions compared across "
        f"<strong>{len(metrics['envs'])}</strong> environments ({envs_list}).",
        f"Largest single-vector drift across the entire dataset: "
        f"<strong>{1 - worst_cos:.2e}</strong> (1 − cosine), between "
        f"<strong>{worst_cos_pair[0]} ↔ {worst_cos_pair[1]}</strong>.",
        f"Largest L2 distance between two embeddings of the same string: "
        f"<strong>{worst_l2:.2e}</strong>, between "
        f"<strong>{worst_l2_pair[0]} ↔ {worst_l2_pair[1]}</strong>.",
    ]

    if knn is not None:
        envs = knn["envs"]
        matrix = knn["agreement_matrix"]
        off_diag = [matrix[a][b] for a in envs for b in envs if a != b]
        if off_diag:
            avg = sum(off_diag) / len(off_diag)
            worst = min(off_diag)
            summary_pieces.append(
                f"Mean off-diagonal top-1 KNN agreement: "
                f"<strong>{avg:.1%}</strong> (worst pair: <strong>{worst:.1%}</strong>)."
            )

    return "<ul>" + "".join(f"<li>{p}</li>" for p in summary_pieces) + "</ul>"


def coverage_block(metrics: dict) -> str:
    rows = [{"env": env, "n vectors": n} for env, n in metrics["coverage"].items()]
    rows.append({"env": "intersection (analyzed)", "n vectors": metrics["n_descriptions"]})
    return pd.DataFrame(rows).to_html(index=False, classes="coverage", border=0)


def self_pair_block(metrics: dict) -> str:
    rows = [
        {"env": env, "min self-cosine": f"{v['min']:.8f}", "max self-cosine": f"{v['max']:.8f}"}
        for env, v in metrics["self_pair_cosine"].items()
    ]
    return pd.DataFrame(rows).to_html(index=False, classes="smoke", border=0)


METHODOLOGY = """
<h3>Methodology</h3>
<p>For each of the five environments, we re-embedded the same ~500 LOINC display-name strings
using the production retriever model
(<code>NCHS/ttc-retriever-mvp</code>, SentenceTransformer, 1024-dim output). Embeddings
were taken on raw text with no L2 normalization (matching the production
<code>embedder.embed()</code> code path). Pairwise metrics are computed on the
intersection of descriptions present across all 5 envs.</p>
<ul>
  <li><strong>cosine similarity</strong> = (a · b) / (‖a‖ · ‖b‖), per description.</li>
  <li><strong>L2 distance</strong> = ‖a − b‖<sub>2</sub>, per description.</li>
  <li><strong>max abs diff</strong> = max element-wise |a − b|, per description.</li>
  <li><strong>outliers</strong> = descriptions with the largest mean per-dimension variance
      across envs.</li>
  <li><strong>KNN top-1 agreement</strong> = for each (env, description), the LOINC code
      that prod OpenSearch returns when the env's vector is the query, compared pairwise
      across envs.</li>
</ul>
<h3>Reproduction</h3>
<p>See <code>docs/spikes/embedding-variability/README.md</code> for full reproduction
commands.</p>
"""

PAGE_TEMPLATE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Embedding Variability — TTC retriever</title>
<style>
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          max-width: 980px; margin: 2rem auto; padding: 0 1rem; color: #222; }}
  h1 {{ margin-bottom: 0; }}
  .subtitle {{ color: #666; margin-top: 0.25rem; }}
  h2 {{ margin-top: 2rem; border-bottom: 1px solid #ddd; padding-bottom: 0.25rem; }}
  table {{ border-collapse: collapse; font-size: 13px; margin: 0.5rem 0 1.5rem 0; }}
  th, td {{ border: 1px solid #e0e0e0; padding: 4px 8px; text-align: right; }}
  th {{ background: #f5f5f5; text-align: center; }}
  td:first-child, th:first-child {{ text-align: left; }}
  .summary, .coverage, .smoke, .outliers {{ width: 100%; }}
  code {{ background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }}
  ul {{ line-height: 1.6; }}
</style>
{plotly_js}
</head>
<body>
<h1>Embedding Variability — TTC retriever</h1>
<p class="subtitle">Generated {generated_at}</p>

<h2>Executive summary</h2>
{exec_summary}

<h2>Coverage</h2>
{coverage}

<h2>Self-pair smoke test</h2>
<p>Each env's vectors against themselves — should be exactly 1.0 for all descriptions.</p>
{self_pair}

<h2>Pairwise summary</h2>
{pair_summary}

<h2>Cosine similarity vs {reference_env}</h2>
{cosine_hist}

<h2>L2 distance (all pairs)</h2>
{l2_hist}

<h2>Top-10 outlier descriptions</h2>
<p>Descriptions where embeddings vary most across the environments.</p>
{outliers}

<h2>Downstream KNN top-1 agreement</h2>
{knn_block}

{methodology}
</body>
</html>
"""


def main() -> int:
    metrics, knn = load_inputs()

    plotly_js = "<script>" + _plotly_js() + "</script>"

    if knn is None:
        knn_block = (
            "<p><em>KNN analysis not run. Re-run with "
            "<code>analyze.py --with-offline-knn</code> (or <code>--with-knn</code> "
            "for the full prod index) to populate this section.</em></p>"
        )
    else:
        knn_block = knn_heatmap(knn)
        if knn.get("mode") == "offline":
            knn_block += (
                "<p><em><strong>Note:</strong> this is the offline proxy — "
                "nearest-neighbor search is over the same 500-description subset, "
                "not the ~1.7M-row prod corpus. It confirms the cross-env drift is "
                "smaller than the gap between distinct LOINCs in this subset, "
                "but cannot rule out edge cases where two prod LOINCs sit close "
                "enough that drift flips the top-1 result.</em></p>"
            )

    page = PAGE_TEMPLATE.format(
        plotly_js=plotly_js,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        exec_summary=exec_summary(metrics, knn),
        coverage=coverage_block(metrics),
        self_pair=self_pair_block(metrics),
        pair_summary=pair_summary_table(metrics),
        cosine_hist=cosine_to_reference_histogram(metrics),
        l2_hist=l2_histogram(metrics),
        reference_env=html.escape(REFERENCE_ENV),
        outliers=outlier_table(metrics),
        knn_block=knn_block,
        methodology=METHODOLOGY,
    )

    report_path = OUTPUTS / "report.html"
    report_path.write_text(page)
    print(f"Wrote {report_path}")
    return 0


def _plotly_js() -> str:
    import plotly.offline as po

    return po.get_plotlyjs()


if __name__ == "__main__":
    raise SystemExit(main())
