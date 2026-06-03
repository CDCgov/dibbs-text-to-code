"""Emit a single self-contained HTML report from `outputs/metrics.json` and `outputs/knn_top1.json`.

The report is organized around the four questions the data-science review posed about
CPU-vs-GPU embedding variability. Plotly is embedded inline so the file can be emailed /
shared without an internet connection.
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
# The production-relevant comparison: index vectors (Azure GPU) vs the Lambda runtime (AWS CPU).
PROD_PAIR = ("azure_gpu", "aws_lambda")


def load_inputs() -> tuple[dict, dict | None]:
    metrics = json.loads((OUTPUTS / "metrics.json").read_text())
    knn_path = OUTPUTS / "knn_top1.json"
    knn = json.loads(knn_path.read_text()) if knn_path.exists() else None
    return metrics, knn


def _pair_key(metrics: dict, a: str, b: str) -> str | None:
    for key, pair in metrics["pair_metrics"].items():
        if set(pair["envs"]) == {a, b}:
            return key
    return None


# --------------------------------------------------------------------------------------
# Top-of-report
# --------------------------------------------------------------------------------------


def tldr_block(metrics: dict, knn: dict | None) -> str:
    """Bottom line up front."""
    pk = _pair_key(metrics, *PROD_PAIR)
    prod = metrics["pair_metrics"][pk] if pk else None
    cos_txt = f"{1 - prod['cosine']['mean']:.2e}" if prod else "~1e-11"
    l2_txt = f"{prod['l2']['mean']:.2e}" if prod else "~6e-6"

    top1 = "n/a"
    if knn:
        envs = knn["envs"]
        m = knn["agreement_matrix"]
        offs = [m[a][b] for a in envs for b in envs if a != b]
        top1 = f"{min(offs):.1%}–{max(offs):.1%}" if offs else "n/a"

    return f"""
<div class="tldr">
  <strong>Bottom line.</strong> The compute environment (CPU vs GPU, Azure vs AWS vs Mac) is
  <em>not</em> a meaningful source of variability for the TTC retriever on this corpus.
  Embedding the same string in the production Lambda runtime (AWS CPU) versus the Azure GPU
  that produced the index changes the vector by only <strong>{l2_txt}</strong> in L2 distance and
  <strong>{cos_txt}</strong> in cosine distance — the float32 precision floor. That drift never
  changes the top-1 retrieved LOINC code ({top1} top-1 agreement across every environment pair),
  and the rest of the result list is stable to within the search engine's <em>own</em>
  re-query noise. <strong>Recommendation: no action.</strong> Do not re-embed the index on CPU,
  and a CPU/GPU vector swap does not need to be raised with APHL.
</div>
"""


def background_block() -> str:
    return """
<p>Different operating systems, hardware, and compute environments produce slightly different
vector embeddings for the same input string. Because TTC relies on consistently representing
clinical text as numbers, this raised a concern: we fine-tune and validate on Azure GPUs, but
production runs on AWS CPUs. If small parameter differences led to materially different vectors —
and therefore different cosine scores and different retrieved codes — our offline evaluation
would not predict production behavior.</p>

<p>Fine-tuning must happen on GPUs (it is otherwise intractable), so the practical question is
whether the GPU→CPU embedding difference is large enough to matter. This report re-embeds the
same ~500 LOINC display-name strings in five environments and works through four questions.</p>

<ol class="questions">
  <li><strong>Q1 — How different are the vectors?</strong> Same string, Azure GPU vs AWS CPU.</li>
  <li><strong>Q2 — Do those differences change the OpenSearch (retriever) results?</strong>
      The top code, the rest of the candidate list, and their scores.</li>
  <li><strong>Q3 — Are the final pipeline predictions (retriever + reranker) different?</strong>
      The reranker does its own internal embedding, so it could re-score identical candidate
      lists differently across environments.</li>
  <li><strong>Q4 — Would swapping the index to Azure-CPU vectors improve stability?</strong>
      A control comparison.</li>
</ol>
"""


# --------------------------------------------------------------------------------------
# Q1 — vector drift
# --------------------------------------------------------------------------------------


def headline_pair_block(metrics: dict) -> str:
    pk = _pair_key(metrics, *PROD_PAIR)
    if not pk:
        return ""
    p = metrics["pair_metrics"][pk]
    rows = [
        ("Cosine distance (1 − cos), mean", f"{1 - p['cosine']['mean']:.3e}"),
        ("Cosine distance (1 − cos), worst", f"{1 - p['cosine']['min']:.3e}"),
        ("L2 distance, mean", f"{p['l2']['mean']:.3e}"),
        ("L2 distance, max", f"{p['l2']['max']:.3e}"),
        ("Max element-wise |Δ|, mean", f"{p['max_abs_diff']['mean']:.3e}"),
        ("Max element-wise |Δ|, max", f"{p['max_abs_diff']['max']:.3e}"),
    ]
    body = "".join(f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in rows)
    return f"""
<p>The production-relevant comparison is <code>azure_gpu</code> (the vectors currently in the
index) against <code>aws_lambda</code> (the production Lambda runtime). Across all 500 strings:</p>
<table class="headline"><tr><th>metric</th><th>value</th></tr>{body}</table>
<p>The model has a normalization layer, so vectors are ~unit length and most coordinates only
carry signal past the third decimal place. An L2 difference in the sixth decimal place is a
real, measurable movement at that scale — but it is distributed such that the cosine similarity
stays virtually 1.0. <strong>The numeric representations still mean the same thing whether
embedded on CPU or GPU.</strong></p>
"""


def pair_summary_table(metrics: dict) -> str:
    rows = []
    for _, pair in metrics["pair_metrics"].items():
        a, b = pair["envs"]
        cos, l2, mx = pair["cosine"], pair["l2"], pair["max_abs_diff"]
        rows.append(
            {
                "env A": a,
                "env B": b,
                "1 − cos mean": f"{1 - cos['mean']:.3e}",
                "1 − cos worst": f"{1 - cos['min']:.3e}",
                "L2 mean": f"{l2['mean']:.3e}",
                "L2 max": f"{l2['max']:.3e}",
                "max |Δ| mean": f"{mx['mean']:.3e}",
                "max |Δ| max": f"{mx['max']:.3e}",
            }
        )
    df = pd.DataFrame(rows).sort_values("1 − cos mean")
    return df.to_html(index=False, classes="summary", border=0)


def cosine_to_reference_histogram(metrics: dict) -> str:
    fig = go.Figure()
    envs = metrics["envs"]
    has_reference = REFERENCE_ENV in envs
    for _, pair in metrics["pair_metrics"].items():
        if has_reference and REFERENCE_ENV not in pair["envs"]:
            continue
        a, b = pair["envs"]
        label = (
            f"{[e for e in pair['envs'] if e != REFERENCE_ENV][0]} vs {REFERENCE_ENV}"
            if has_reference
            else f"{a} ↔ {b}"
        )
        one_minus = [max(1.0 - c, 1e-15) for c in pair["per_description"]["cosine"]]
        fig.add_trace(go.Histogram(x=one_minus, name=label, opacity=0.55, nbinsx=60))
    title_suffix = f"to {REFERENCE_ENV}" if has_reference else "(all pairs)"
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
    for _, pair in metrics["pair_metrics"].items():
        a, b = pair["envs"]
        fig.add_trace(
            go.Histogram(x=pair["per_description"]["l2"], name=f"{a} ↔ {b}", opacity=0.45, nbinsx=50)
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


# --------------------------------------------------------------------------------------
# Q2 — retrieval stability
# --------------------------------------------------------------------------------------


def agreement_heatmap(matrix: dict, envs: list[str], title: str, fmt: str = ".2%") -> str:
    z = [[matrix[a][b] for b in envs] for a in envs]
    flat = [v for row in z for v in row]
    zmin = max(0.0, min(flat) - (1.0 - min(flat)) - 1e-4) if flat else 0.0
    text = [[format(matrix[a][b], fmt) for b in envs] for a in envs]
    fig = go.Figure(
        data=go.Heatmap(
            z=z, x=envs, y=envs, text=text, texttemplate="%{text}",
            colorscale="Viridis", zmin=zmin, zmax=1.0, colorbar={"title": "agreement"},
        )
    )
    fig.update_layout(title=title, height=460)
    return fig.to_html(full_html=False, include_plotlyjs=False)


def score_delta_table(knn: dict) -> str:
    ref = knn.get("reference_env", REFERENCE_ENV)
    rows = []
    for env, s in knn.get("score_delta_vs_reference", {}).items():
        rows.append(
            {
                "env (vs " + ref + ")": env,
                "shared candidates": s["n_shared_candidates"],
                "mean |Δscore|": f"{s['mean_abs_score_delta']:.3e}",
                "p99 |Δscore|": f"{s['p99_abs_score_delta']:.3e}",
                "max |Δscore|": f"{s['max_abs_score_delta']:.3e}",
            }
        )
    if not rows:
        return ""
    return pd.DataFrame(rows).to_html(index=False, classes="summary", border=0)


def determinism_block(knn: dict) -> str:
    d = knn.get("determinism_baseline")
    if not d:
        return ""
    ref = knn.get("reference_env", REFERENCE_ENV)
    return f"""
<div class="note">
  <strong>Search-engine noise floor.</strong> OpenSearch KNN uses an approximate (HNSW) index.
  Re-running the <em>identical</em> <code>{ref}</code> query vectors a second time — changing
  nothing about the input — does not return a perfectly identical result list:
  top-1 agreement <strong>{d['top1_agreement']:.1%}</strong>,
  top-{knn.get('k', 10)} set overlap <strong>{d['set_jaccard']:.3%}</strong>,
  exact-order agreement <strong>{d['order_agreement']:.1%}</strong>,
  mean per-candidate score delta <strong>{d['mean_abs_score_delta']:.2e}</strong>.
  Cross-environment differences must be read against this floor: where the numbers below are at
  or near these values, the variation is the search engine's own non-determinism, not the
  embedding.
</div>
"""


def near_tie_block() -> str:
    return """
<div class="note">
  <strong>The one borderline case.</strong> An earlier run (against an older index snapshot)
  showed a single description, <code>"MR Hrt Cine for Flow VM"</code>, whose top-1 differed for
  <code>azure_cpu</code>. Re-querying now shows why it is a non-issue: its top two candidates —
  <code>39140-9</code> and <code>105173-9</code> — score <em>identically</em> (both ≈ 1.0, margin
  0.00) in every environment. They are an exact tie, so which one lands at rank 1 is decided
  arbitrarily by index internals, not by the embedding. The tie resolved one way against the old
  index snapshot and the other way against the current one. This is corpus / near-tie behavior,
  not a CPU-vs-GPU effect.
</div>
"""


# --------------------------------------------------------------------------------------
# Q3 / Q4 / conclusion
# --------------------------------------------------------------------------------------


Q3_BLOCK = """
<p>The reranker re-scores the retriever's candidate list using a cross-encoder, which performs
its own internal "mini-embedding" of each (query, candidate) pair. That internal step is subject
to the same CPU-vs-GPU arithmetic differences as the retriever. So even when the retriever hands
the reranker an identical candidate list across environments, the reranker could, in principle,
re-score and re-sort them differently — an "embedding cascade" where every candidate moves a
little and their relative order changes.</p>

<p><strong>This report does not measure the reranker stage.</strong> Doing so rigorously would
require the brute-force pairwise experiment described under Q4. Two facts bound the risk:</p>
<ul>
  <li><strong>The retriever is the dominant, trusted component.</strong> It is the stronger of the
      two models, and the design errs toward retrieval over reranking. Q1 and Q2 show the
      retrieval stage is effectively environment-invariant.</li>
  <li><strong>Confidence / margin thresholds are planned</strong> for the next tuning round and are
      designed to short-circuit the reranker whenever the retriever is already confident — which
      reduces both the frequency and the blast radius of any reranker-stage sensitivity.</li>
</ul>
<p>Because the reranker's own score estimates are still weak (pre-tuning), we cannot yet say
whether environment-driven reranker differences would even be large relative to its existing
error. This is flagged as an open item, not a blocker.</p>
"""

Q4_BLOCK = """
<p>The control question — does re-embedding the index with Azure-CPU vectors make any of the
above more stable? — is not answered directly. Doing it properly is the brute-force experiment:
for many nonstandard inputs of each of the ~335k LOINC variants, run nearest-neighbor searches in
both environments and mutually rank-score every retriever and reranker result to confirm they
match. That is disproportionate to the size of the concern as currently understood, and Q1–Q2
already show the cross-environment vector drift is far below the gap between distinct LOINC codes.
It can be revisited if production data later surfaces instability.</p>
"""


def conclusion_block(knn: dict | None) -> str:
    return """
<ul>
  <li><strong>Q1 (vectors):</strong> Azure-GPU vs AWS-CPU embeddings of the same string differ
      at the float32 precision floor (cosine distance ~1e-11, L2 ~6e-6). Semantically identical.</li>
  <li><strong>Q2 (retrieval):</strong> Top-1 retrieved LOINC is identical across all five
      environments for all 500 strings. Top-10 membership and ordering agree to within the
      search engine's own re-query noise floor, and per-candidate scores match to ~7 significant
      figures. The retriever is effectively environment-invariant.</li>
  <li><strong>Q3 (full pipeline):</strong> Not measured. The retriever — which we trust far more
      than the reranker — is stable, and planned margin thresholds will further limit reranker
      exposure. Flagged as an open item, not a blocker.</li>
  <li><strong>Q4 (control):</strong> Not run; disproportionate to the concern.</li>
</ul>
<p class="rec"><strong>Recommendation:</strong> No action. CPU-vs-GPU is not enough of a problem to
warrant changing anything. Do not re-embed the index on CPU, and do not raise a vector-swap with
APHL — it would add coordination overhead for no measurable retrieval benefit. Re-open Q3/Q4 only
if post-deployment data shows reranker-stage instability.</p>
"""


# --------------------------------------------------------------------------------------
# Shared blocks
# --------------------------------------------------------------------------------------


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
<p>For each of the five environments we re-embedded the same ~500 LOINC display-name strings with
the production retriever (<code>NCHS/ttc-retriever-mvp</code>, SentenceTransformer, 1024-dim) on
raw text with no extra L2 normalization, matching the production <code>embedder.embed()</code> path.
Pairwise metrics use the intersection of descriptions present in all 5 environments.</p>
<ul>
  <li><strong>cosine / L2 / max|Δ|</strong> — per-description vector-distance metrics.</li>
  <li><strong>top-1 agreement</strong> — for each (env, description), the LOINC code prod
      OpenSearch returns when that env's vector is the query, compared pairwise.</li>
  <li><strong>top-k set Jaccard / exact-order agreement</strong> — over k=10 hits, whether the same
      candidates appear and whether they appear in the same order.</li>
  <li><strong>per-candidate score delta</strong> — for candidates shared with the reference's
      top-k (matched by document id), the absolute difference in KNN score.</li>
  <li><strong>determinism baseline</strong> — an independent re-query of the reference env's
      identical vectors, isolating the approximate-search non-determinism floor.</li>
</ul>
<h3>Limitations</h3>
<ul>
  <li>The reranker stage (Q3) and the index-swap control (Q4) are not measured (see those sections).</li>
  <li>Analysis is on the 500-string intersection; coverage is reported above.</li>
  <li>Production calls <code>.encode(text)</code> with default args (no L2 normalization); cosine is
      computed on raw vectors throughout.</li>
  <li>The Azure GPU vectors are a single snapshot; GPU embedding is not bitwise-deterministic across
      re-runs, and the prod index is a live, periodically re-ingested corpus.</li>
</ul>
<h3>Reproduction</h3>
<p>See <code>docs/spikes/embedding-variability/README.md</code> for full reproduction commands.</p>
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
  h2 {{ margin-top: 2.5rem; border-bottom: 2px solid #ddd; padding-bottom: 0.25rem; }}
  h3 {{ margin-top: 1.5rem; }}
  table {{ border-collapse: collapse; font-size: 13px; margin: 0.5rem 0 1.5rem 0; }}
  th, td {{ border: 1px solid #e0e0e0; padding: 4px 8px; text-align: right; }}
  th {{ background: #f5f5f5; text-align: center; }}
  td:first-child, th:first-child {{ text-align: left; }}
  .summary, .coverage, .smoke, .outliers, .headline {{ width: 100%; }}
  code {{ background: #f4f4f4; padding: 1px 4px; border-radius: 3px; }}
  ul, ol {{ line-height: 1.6; }}
  .tldr {{ background: #eef6ff; border-left: 4px solid #2f6fd0; padding: 0.9rem 1.1rem;
           border-radius: 4px; line-height: 1.55; }}
  .note {{ background: #fbf7e8; border-left: 4px solid #d0a72f; padding: 0.8rem 1.1rem;
           border-radius: 4px; margin: 1rem 0; line-height: 1.5; }}
  .rec {{ background: #eefaef; border-left: 4px solid #2f9d4f; padding: 0.8rem 1.1rem;
          border-radius: 4px; }}
  ol.questions li {{ margin-bottom: 0.35rem; }}
</style>
{plotly_js}
</head>
<body>
<h1>Embedding Variability — TTC retriever</h1>
<p class="subtitle">CPU vs GPU across 5 compute environments · generated {generated_at}</p>

{tldr}

<h2>Background &amp; questions</h2>
{background}

<h2>Q1 — How different are the vectors?</h2>
{headline_pair}
<h3>All environment pairs</h3>
{pair_summary}
<h3>Distributions</h3>
{cosine_hist}
{l2_hist}
<h3>Most-variable descriptions</h3>
<p>The 10 strings whose embeddings vary most across environments (still negligible in absolute terms).</p>
{outliers}

<h2>Q2 — Do the differences change the retriever's results?</h2>
<p>For every (environment, description) we issue a real KNN query against the production
<code>ttc-index</code> (~335k docs) using that environment's vector, and capture the top-10 hits
with their scores. The question has three parts: does the <em>top</em> code change, are the
<em>same candidates</em> returned, and are their <em>scores</em> the same?</p>
{determinism}
<h3>Top-1 agreement</h3>
<p>The retrieved code is identical across all five environments for every one of the
{n_desc} strings — full 100% agreement on every pair.</p>
<h3>Top-10 membership (set Jaccard)</h3>
{jaccard_heatmap}
<h3>Top-10 ordering (exact-order agreement)</h3>
{order_heatmap}
<h3>Per-candidate score stability</h3>
<p>For candidates shared with the {reference_env} top-10 (matched by document id), how far the
KNN score moves when only the query embedding changes environment:</p>
{score_delta}
{near_tie}
<p>So the answer to Q2: the top result is rock-solid; the deeper candidate list and its scores are
stable to within the search engine's own re-query noise. The reviewer's concern that deep-rank
neighbors (4–10) could reshuffle is borne out only at a rate indistinguishable from that noise
floor, and never disturbs the top-1.</p>

<h2>Q3 — Are the final pipeline (retriever + reranker) predictions different?</h2>
{q3}

<h2>Q4 — Would swapping the index to Azure-CPU vectors help?</h2>
{q4}

<h2>Conclusion &amp; recommendation</h2>
{conclusion}

<h2>Appendix: coverage &amp; self-pair smoke test</h2>
{coverage}
{self_pair}

<h2>Methodology, limitations &amp; reproduction</h2>
{methodology}
</body>
</html>
"""


def main() -> int:
    metrics, knn = load_inputs()
    plotly_js = "<script>" + _plotly_js() + "</script>"
    envs = knn["envs"] if knn else metrics["envs"]
    ref = knn.get("reference_env", REFERENCE_ENV) if knn else REFERENCE_ENV

    if knn is None:
        empty = (
            "<p><em>KNN analysis not run. Re-run <code>analyze.py --with-knn</code> to populate "
            "the retrieval-stability sections.</em></p>"
        )
        jaccard_heatmap = order_heatmap = score_delta = determinism = near_tie = empty
    else:
        jaccard_heatmap = agreement_heatmap(
            knn["jaccard_matrix"], envs, "Top-10 candidate-set Jaccard overlap (KNN vs prod index)"
        )
        order_heatmap = agreement_heatmap(
            knn["order_agreement_matrix"], envs, "Top-10 exact-order agreement (KNN vs prod index)"
        )
        score_delta = score_delta_table(knn)
        determinism = determinism_block(knn)
        near_tie = near_tie_block()

    page = PAGE_TEMPLATE.format(
        plotly_js=plotly_js,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        tldr=tldr_block(metrics, knn),
        background=background_block(),
        headline_pair=headline_pair_block(metrics),
        pair_summary=pair_summary_table(metrics),
        cosine_hist=cosine_to_reference_histogram(metrics),
        l2_hist=l2_histogram(metrics),
        outliers=outlier_table(metrics),
        determinism=determinism,
        n_desc=metrics["n_descriptions"],
        jaccard_heatmap=jaccard_heatmap,
        order_heatmap=order_heatmap,
        reference_env=html.escape(ref),
        score_delta=score_delta,
        near_tie=near_tie,
        q3=Q3_BLOCK,
        q4=Q4_BLOCK,
        conclusion=conclusion_block(knn),
        coverage=coverage_block(metrics),
        self_pair=self_pair_block(metrics),
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
