from __future__ import annotations

from html import escape
from pathlib import Path
import json
from typing import Any


def write_reports(report: dict[str, Any], output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    (output / "comparison.json").write_text(
        json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output / "comparison.html").write_text(render_html(report), encoding="utf-8")


def render_html(report: dict[str, Any]) -> str:
    summary = report["summary"]
    database_release = report["database_release_alignment"]
    synthetic_contract = report.get("comparison_mode") == "synthetic_contract"
    counterpart_key = "candidate" if synthetic_contract else "actual"
    counterpart_heading = "Planned contract shape" if synthetic_contract else "Observed"
    kicker = "Synthetic contract exercise" if synthetic_contract else "Observed evidence comparison"
    evidence_note = (
        "This portable report exercises released comparison contracts. Its authority "
        "is synthetic contract shape; environment-observed closure remains separate "
        "and unasserted, and production authorization effect is none."
        if synthetic_contract
        else "This report compares caller-supplied observed evidence under the released admission contract."
    )
    rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(item['path'])}</code></td>"
        f"<td><span class=\"pill {escape(item['classification'])}\">{escape(item['classification'])}</span></td>"
        f"<td>{'Critical' if item['critical'] else 'Standard'}</td>"
        f"<td>{escape(item['value_visibility'])}</td>"
        f"<td>{escape(item['rationale'])}</td>"
        f"<td><pre>{escape(json.dumps(item['expected'], indent=2, sort_keys=True, allow_nan=False))}</pre></td>"
        f"<td><pre>{escape(json.dumps(item[counterpart_key], indent=2, sort_keys=True, allow_nan=False))}</pre></td>"
        "</tr>"
        for item in report["differences"]
    )
    embedded = escape(json.dumps(report, sort_keys=True, allow_nan=False))
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Comparative evidence · {escape(report['scenario_id'])}</title>
<style>
:root {{ color-scheme: light; --ink:#152433; --paper:#f4f0e8; --blue:#2357d9; --coral:#dd6b55; --line:#b8c2cc; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 ui-sans-serif,system-ui,sans-serif; }}
main {{ max-width:1500px; margin:auto; padding:3rem; }}
h1 {{ font-size:clamp(2rem,5vw,4.5rem); line-height:.95; max-width:13ch; letter-spacing:-.04em; }}
.kicker {{ color:var(--blue); font-weight:700; letter-spacing:.09em; text-transform:uppercase; }}
.summary {{ display:grid; grid-template-columns:repeat(4,minmax(10rem,1fr)); gap:1rem; margin:2rem 0; }}
.card {{ border:1px solid var(--line); border-radius:1rem; padding:1.2rem; background:#fff9; }}
.value {{ display:block; font-size:2.4rem; font-weight:750; }}
table {{ width:100%; border-collapse:collapse; background:#fff9; }}
th,td {{ border:1px solid var(--line); padding:.8rem; text-align:left; vertical-align:top; }}
th {{ background:#e7ecf6; }}
pre {{ margin:0; max-width:34ch; overflow:auto; white-space:pre-wrap; }}
.pill {{ display:inline-block; border:1px solid currentColor; border-radius:99rem; padding:.15rem .55rem; }}
.actual_defect,.shared_specification_violation {{ color:#a82d21; }}
.desired_divergence,.simulation_fault {{ color:#176b45; }}
footer {{ margin-top:2rem; font-size:.85rem; color:#536270; }}
@media(max-width:900px) {{ main{{padding:1rem}} .summary{{grid-template-columns:1fr 1fr}} table{{display:block;overflow:auto}} }}
</style>
</head>
<body>
<main>
<p class="kicker">{escape(kicker)}</p>
<h1>{escape(report['scenario_id'])}</h1>
<p>{escape(evidence_note)}</p>
<section class="summary" aria-label="Comparison summary">
  <div class="card"><span class="value">{summary['leaf_paths_compared']}</span>paths compared</div>
  <div class="card"><span class="value">{summary['converged_paths']}</span>converged</div>
  <div class="card"><span class="value">{summary['material_differences']}</span>material differences</div>
  <div class="card"><span class="value">{summary['critical_differences']}</span>critical differences</div>
</section>
<h2>Database release alignment</h2>
<section class="summary" aria-label="Database release alignment">
  <div class="card"><strong>{escape(database_release['target_status'])}</strong><br>target status</div>
  <div class="card"><strong>{'Aligned' if database_release['data_contract_aligned'] else 'Review'}</strong><br>data contract</div>
  <div class="card"><strong>{'Aligned' if database_release['migration_manifest_aligned'] else 'Review'}</strong><br>migration manifest</div>
  <div class="card"><strong>{'Aligned' if database_release['migration_mechanism_aligned'] else 'Distinct'}</strong><br>migration mechanism</div>
  <div class="card"><strong>{'Aligned' if database_release['schema_aligned'] else 'Review'}</strong><br>target schema</div>
</section>
<h2>Adjudication surface</h2>
<table>
<thead><tr><th>Path</th><th>Classification</th><th>Critical</th><th>Value visibility</th><th>Rationale</th><th>Simulation</th><th>{escape(counterpart_heading)}</th></tr></thead>
<tbody>{rows or '<tr><td colspan="7">All compared paths converged.</td></tr>'}</tbody>
</table>
<footer>
  <p>Report digest: <code>{escape(report['report_digest'])}</code></p>
  <details><summary>Machine-readable report</summary><pre>{embedded}</pre></details>
</footer>
</main>
</body>
</html>
"""
