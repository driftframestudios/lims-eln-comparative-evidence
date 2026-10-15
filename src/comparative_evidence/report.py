from __future__ import annotations

from html import escape
from pathlib import Path
import json
from typing import Any
from urllib.parse import urlsplit

from .publication import render_public_boundary
from .legacy_json import REPORT_BUDGET, HTML_BYTES, RepresentationCapacityError, validate_representation


def write_reports(
    report: dict[str, Any],
    output: Path,
    *,
    canonical_url: str | None = None,
) -> None:
    """Publish a complete immutable pair into an empty or fresh directory."""
    from .artifact_boundary import _report_inventory_at
    from .filesystem_publication import publish_report

    validate_representation(report, REPORT_BUDGET)
    json_payload = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    if len(json_payload) > REPORT_BUDGET.bytes:
        raise RepresentationCapacityError("report_bytes")
    html_payload = render_html(report, canonical_url=canonical_url).encode("utf-8")
    if len(html_payload) > HTML_BYTES:
        raise RepresentationCapacityError("report_bytes")
    payloads = {"comparison.json": json_payload, "comparison.html": html_payload}
    limits = {name: len(payload) for name, payload in payloads.items()}
    publish_report(payloads, output, lambda descriptor: _report_inventory_at(descriptor, limits))


def render_html(
    report: dict[str, Any],
    *,
    canonical_url: str | None = None,
) -> str:
    validate_representation(report, REPORT_BUDGET)
    if report.get("comparison_mode") == "simulated_verification":
        return _render_simulated_verification_html(
            report,
            canonical_url=canonical_url,
        )
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
        f"<td class=\"classification-column\"><span class=\"pill {escape(item['classification'])}\">{escape(item['classification'])}</span></td>"
        f"<td>{'Critical' if item['critical'] else 'Standard'}</td>"
        f"<td>{escape(item['value_visibility'])}</td>"
        f"<td>{escape(item['rationale'])}</td>"
        f"<td><pre>{escape(json.dumps(item['expected'], indent=2, sort_keys=True, allow_nan=False))}</pre></td>"
        f"<td><pre>{escape(json.dumps(item[counterpart_key], indent=2, sort_keys=True, allow_nan=False))}</pre></td>"
        "</tr>"
        for item in report["differences"]
    )
    embedded = escape(json.dumps(report, sort_keys=True, allow_nan=False))
    canonical_markup = ""
    if canonical_url is not None:
        parsed = urlsplit(canonical_url)
        if (
            parsed.scheme != "https"
            or not parsed.netloc
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "portable report canonical URL requires one credential-free HTTPS location"
            )
        canonical_markup = (
            f'<link rel="canonical" href="{escape(canonical_url, quote=True)}">\n'
        )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{canonical_markup}<title>Comparative evidence · {escape(report['scenario_id'])}</title>
<style>
:root {{ color-scheme: light; --ink:#152433; --paper:#f4f0e8; --blue:#2357d9; --coral:#dd6b55; --line:#b8c2cc; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 ui-sans-serif,system-ui,sans-serif; overflow-wrap:anywhere; }}
main {{ max-width:1500px; margin:auto; padding:3rem; }}
.skip-link {{ position:absolute; left:.75rem; top:.75rem; transform:translateY(-200%); background:#fff; color:var(--ink); padding:.55rem .8rem; z-index:2; }}
.skip-link:focus {{ transform:none; }}
h1 {{ font-size:clamp(2rem,5vw,4.5rem); line-height:.95; max-width:13ch; letter-spacing:-.04em; }}
.kicker {{ color:var(--blue); font-weight:700; letter-spacing:.09em; text-transform:uppercase; }}
.summary {{ display:grid; grid-template-columns:repeat(4,minmax(10rem,1fr)); gap:1rem; margin:2rem 0; }}
.card {{ border:1px solid var(--line); border-radius:1rem; padding:1.2rem; background:#fff9; }}
.value {{ display:block; font-size:2.4rem; font-weight:750; }}
table {{ width:100%; min-width:72rem; border-collapse:collapse; background:#fff9; }}
th,td {{ border:1px solid var(--line); padding:.8rem; text-align:left; vertical-align:top; }}
th {{ background:#e7ecf6; }}
.classification-column {{ min-width:13rem; overflow-wrap:normal; }}
.table-instructions {{ margin:.25rem 0 .75rem; color:#536270; }}
.table-scroll {{ width:100%; max-width:100%; overflow-x:auto; overscroll-behavior-inline:contain; -webkit-overflow-scrolling:touch; }}
.table-scroll:focus-visible {{ outline:3px solid var(--blue); outline-offset:3px; }}
pre {{ margin:0; max-width:34ch; overflow:auto; white-space:pre-wrap; }}
.pill {{ display:inline-block; border:1px solid currentColor; border-radius:99rem; padding:.15rem .55rem; white-space:nowrap; }}
.actual_defect,.shared_specification_violation {{ color:#a82d21; }}
.desired_divergence,.simulation_fault {{ color:#176b45; }}
footer {{ margin-top:2rem; font-size:.85rem; color:#536270; }}
.public-boundary {{ margin-top:2rem; padding-top:1.5rem; border-top:1px solid var(--line); }}
.public-boundary pre {{ margin:.5rem 0; max-width:none; white-space:pre-wrap; overflow-wrap:anywhere; }}
.public-boundary .attribution {{ margin-top:1rem; }}
@media(max-width:900px) {{ main{{padding:1rem}} .summary{{grid-template-columns:1fr}} }}
</style>
</head>
<body>
<a class="skip-link" href="#comparison-content">Skip to comparison</a>
<main id="comparison-content">
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
<h2 id="adjudication-heading">Adjudication surface</h2>
<p class="table-instructions" id="adjudication-instructions">Scroll horizontally inside the comparison table to review every field.</p>
<div class="table-scroll" role="region" aria-labelledby="adjudication-heading" aria-describedby="adjudication-instructions" tabindex="0">
<table>
<thead><tr><th>Path</th><th class="classification-column">Classification</th><th>Critical</th><th>Value visibility</th><th>Rationale</th><th>Simulation</th><th>{escape(counterpart_heading)}</th></tr></thead>
<tbody>{rows or '<tr><td colspan="7">All compared paths converged.</td></tr>'}</tbody>
</table>
</div>
<footer>
  <p>Report digest: <code>{escape(report['report_digest'])}</code></p>
  <details><summary>Machine-readable report</summary><pre>{embedded}</pre></details>
  {render_public_boundary()}
</footer>
</main>
</body>
</html>
"""


def _render_simulated_verification_html(
    report: dict[str, Any],
    *,
    canonical_url: str | None = None,
) -> str:
    """Render the shared-result report without implying observed evidence."""

    summary = report["summary"]
    counts = summary["classification_counts"]
    comparisons = report["comparisons"]
    rows = "\n".join(
        "<tr>"
        f"<td><code>{escape(item['path'])}</code></td>"
        f"<td class=\"classification-column\"><span class=\"pill {escape(item['classification'])}\">"
        f"{escape(item['classification'])}</span></td>"
        f"<td>{escape(item['rationale'])}</td>"
        f"<td><pre>{escape(json.dumps(item['implementation'], indent=2, sort_keys=True, allow_nan=False))}</pre></td>"
        f"<td><pre>{escape(json.dumps(item['simulation'], indent=2, sort_keys=True, allow_nan=False))}</pre></td>"
        "</tr>"
        for item in comparisons
    )
    implementation = report["implementation"]
    simulation = report["simulation"]
    embedded = escape(json.dumps(report, sort_keys=True, allow_nan=False))
    canonical_markup = _canonical_markup(canonical_url)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
{canonical_markup}<title>Golden Specimen verification · {escape(report['scenario_id'])}</title>
<style>
:root {{ color-scheme:light; --ink:#152433; --paper:#f4f0e8; --blue:#2357d9; --green:#176b45; --amber:#8b5a00; --red:#a82d21; --line:#b8c2cc; }}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.5 ui-sans-serif,system-ui,sans-serif; overflow-wrap:anywhere; }}
main {{ max-width:1500px; margin:auto; padding:3rem; }}
.skip-link {{ position:absolute; left:.75rem; top:.75rem; transform:translateY(-200%); background:#fff; color:var(--ink); padding:.55rem .8rem; z-index:2; }}
.skip-link:focus {{ transform:none; }}
h1 {{ font-size:clamp(2rem,5vw,4.5rem); line-height:.95; max-width:14ch; letter-spacing:-.04em; }}
.kicker {{ color:var(--blue); font-weight:700; letter-spacing:.09em; text-transform:uppercase; }}
.summary,.sources {{ display:grid; grid-template-columns:repeat(3,minmax(12rem,1fr)); gap:1rem; margin:2rem 0; }}
.sources {{ grid-template-columns:repeat(2,minmax(16rem,1fr)); }}
.card {{ border:1px solid var(--line); border-radius:1rem; padding:1.2rem; background:#fff9; }}
.value {{ display:block; font-size:2.4rem; font-weight:750; }}
.coordinate {{ margin:.4rem 0 0; font-size:.88rem; }}
table {{ width:100%; min-width:68rem; border-collapse:collapse; background:#fff9; }}
th,td {{ border:1px solid var(--line); padding:.8rem; text-align:left; vertical-align:top; }}
th {{ background:#e7ecf6; }}
.classification-column {{ min-width:13rem; overflow-wrap:normal; }}
.table-instructions {{ margin:.25rem 0 .75rem; color:#536270; }}
.table-scroll {{ width:100%; max-width:100%; overflow-x:auto; overscroll-behavior-inline:contain; -webkit-overflow-scrolling:touch; }}
.table-scroll:focus-visible {{ outline:3px solid var(--blue); outline-offset:3px; }}
pre {{ margin:0; max-width:34ch; overflow:auto; white-space:pre-wrap; }}
.pill {{ display:inline-block; border:1px solid currentColor; border-radius:99rem; padding:.15rem .55rem; white-space:nowrap; }}
.agreement {{ color:var(--green); }}
.explainable_variation {{ color:var(--amber); }}
.material_divergence {{ color:var(--red); }}
footer {{ margin-top:2rem; font-size:.85rem; color:#536270; }}
.public-boundary {{ margin-top:2rem; padding-top:1.5rem; border-top:1px solid var(--line); }}
.public-boundary pre {{ margin:.5rem 0; max-width:none; white-space:pre-wrap; overflow-wrap:anywhere; }}
.public-boundary .attribution {{ margin-top:1rem; }}
@media(max-width:900px) {{ main{{padding:1rem}} .summary,.sources{{grid-template-columns:1fr}} }}
</style>
</head>
<body>
<a class="skip-link" href="#comparison-content">Skip to comparison</a>
<main id="comparison-content">
<p class="kicker">Shared-result verification</p>
<h1>Golden Specimen</h1>
<p>Two synthetic producers are compared through the same released result projection. The durable input is a Comparator-owned snapshot generated from accepted Enterprise source; the selected-future input is the accepted Simulation observation. Environment-observed evidence keeps its independent provenance and acceptance route.</p>
<section class="summary" aria-label="Comparison summary">
  <div class="card"><span class="value">{counts['agreement']}</span>agreements</div>
  <div class="card"><span class="value">{counts['explainable_variation']}</span>explainable variations</div>
  <div class="card"><span class="value">{counts['material_divergence']}</span>material divergences</div>
</section>
<h2>Source coordinates</h2>
<section class="sources" aria-label="Producer source coordinates">
  <div class="card"><strong>Durable workbench snapshot</strong><p class="coordinate">Release <code>{escape(implementation['coordinate']['release'])}</code><br>Commit <code>{escape(implementation['coordinate']['commit'])}</code><br>Observation <code>{escape(implementation['observation_digest'])}</code><br>Projection <code>{escape(implementation['projection_digest'])}</code></p></div>
  <div class="card"><strong>Selected-future observation</strong><p class="coordinate">Release <code>{escape(simulation['coordinate']['release'])}</code><br>Commit <code>{escape(simulation['coordinate']['commit'])}</code><br>Observation <code>{escape(simulation['observation_digest'])}</code><br>Projection <code>{escape(simulation['projection_digest'])}</code></p></div>
</section>
<h2 id="adjudication-heading">Decision-relevant result</h2>
<p class="table-instructions" id="adjudication-instructions">Scroll horizontally inside the comparison table to review every shared field.</p>
<div class="table-scroll" role="region" aria-labelledby="adjudication-heading" aria-describedby="adjudication-instructions" tabindex="0">
<table>
<thead><tr><th>Path</th><th class="classification-column">Classification</th><th>Why</th><th>Durable workbench</th><th>Selected future</th></tr></thead>
<tbody>{rows}</tbody>
</table>
</div>
<footer>
  <p>Compared {summary['leaf_paths_compared']} closed projection paths. Report digest: <code>{escape(report['report_digest'])}</code></p>
  <details><summary>Machine-readable report</summary><pre>{embedded}</pre></details>
  {render_public_boundary()}
</footer>
</main>
</body>
</html>
"""


def _canonical_markup(canonical_url: str | None) -> str:
    if canonical_url is None:
        return ""
    parsed = urlsplit(canonical_url)
    if (
        parsed.scheme != "https"
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "portable report canonical URL requires one credential-free HTTPS location"
        )
    return f'<link rel="canonical" href="{escape(canonical_url, quote=True)}">\n'
