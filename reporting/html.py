"""HTML report generator for MutaGuard.

Produces a single self-contained HTML file: inline CSS, 
no external dependencies, no JavaScript frameworks.
"""
from __future__ import annotations

import html
from pathlib import Path

from core.results import MutationReport
from core.runner import MutantResult


def generate_html_report(
    report: MutationReport,
    source_text: str,
    output_path: Path,
) -> None:
    """Render *report* as a self-contained HTML file at *output_path*."""
    body = _build_body(report, source_text)
    page = (
        _HTML_TEMPLATE
        .replace("{{TITLE}}", html.escape(report.source_file))
        .replace("{{BODY}}",  body)
    )
    output_path.write_text(page, encoding="utf-8")


# ---- Body html builder ------------------------------------------------------

def _build_body(report: MutationReport, source_text: str) -> str:
    score       = report.mutation_score * 100
    score_class = "good" if score >= 80 else ("warn" if score >= 50 else "bad")
    sections: list[str] = []

    # Summary card
    sections.append(f"""
    <section class="card summary">
      <h2>Summary</h2>
      <div class="score {score_class}">{score:.1f}%</div>
      <p class="score-label">Mutation Score</p>
      <table class="stat-table">
        <tr><td>Total Mutants</td>  <td class="num">{report.total:,}</td></tr>
        <tr><td>Killed</td>         <td class="num killed">{report.killed:,}</td></tr>
        <tr><td>Survived</td>       <td class="num survived">{report.survived:,}</td></tr>
        <tr><td>Timeout</td>        <td class="num timeout">{report.timeout:,}</td></tr>
        <tr><td>Equivalent</td>     <td class="num equiv">{report.equivalent_count:,}</td></tr>
        <tr><td>Error</td>          <td class="num">{report.error:,}</td></tr>
        <tr><td>Elapsed</td>        <td class="num">{report.elapsed_seconds:.1f}s</td></tr>
      </table>
    </section>""")

    # Operators
    op_rows = ""
    for name, s in report.operator_stats().items():
        score_str = f"{s.score * 100:.0f}%" if s.score is not None else "N/A"
        op_rows += f"""
        <tr>
          <td>{html.escape(name)}</td>
          <td class="num">{s.total}</td>
          <td class="num killed">{s.killed}</td>
          <td class="num survived">{s.survived}</td>
          <td class="num timeout">{s.timeout}</td>
          <td class="num equiv">{s.equivalent}</td>
          <td class="num">{score_str}</td>
        </tr>"""

    sections.append(f"""
    <section class="card">
      <h2>Operator Breakdown</h2>
      <table class="breakdown-table">
        <thead>
          <tr>
            <th>Operator</th><th>Total</th><th>Killed</th>
            <th>Survived</th><th>Timeout</th><th>Equiv</th><th>Score</th>
          </tr>
        </thead>
        <tbody>{op_rows}</tbody>
      </table>
    </section>""")

    # Source view 
    sections.append(_build_source_section(report, source_text))

    # Surviving mutants table
    if report.surviving_mutants:
        rows = "".join(
            f"""<tr>
              <td>{r.mutant.line_number}</td>
              <td><code>{html.escape(r.mutant.original_node)}</code></td>
              <td>-&gt;</td>
              <td><code>{html.escape(r.mutant.mutated_node)}</code></td>
              <td>{html.escape(r.mutant.operator)}</td>
            </tr>"""
            for r in report.surviving_mutants
        )
        sections.append(f"""
        <section class="card">
          <h2>Surviving Mutants ({len(report.surviving_mutants)})</h2>
          <table class="breakdown-table">
            <thead>
              <tr><th>Line</th><th>Original</th><th></th>
                  <th>Mutated</th><th>Operator</th></tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>""")

    # Equivalent mutants
    if report.equivalent_results:
        eq_rows = "".join(
            f"""<tr>
              <td>{r.mutant.line_number}</td>
              <td><code>{html.escape(r.mutant.original_node)}
                  -&gt; {html.escape(r.mutant.mutated_node)}</code></td>
              <td>{html.escape(eq.reason.name if eq.reason else '')}</td>
              <td>{html.escape(eq.explanation)}</td>
            </tr>"""
            for r, eq in report.equivalent_results
        )
        sections.append(f"""
        <section class="card">
          <h2>Equivalent Mutants ({len(report.equivalent_results)})</h2>
          <p class="muted">Excluded from mutation score.</p>
          <table class="breakdown-table">
            <thead>
              <tr><th>Line</th><th>Mutation</th>
                  <th>Reason</th><th>Explanation</th></tr>
            </thead>
            <tbody>{eq_rows}</tbody>
          </table>
        </section>""")

    return "\n".join(sections)


def _build_source_section(report: MutationReport, source_text: str) -> str:
    """Build the annotated source view section."""
    # Map line number, list of results on that line
    line_results: dict[int, list[MutantResult]] = {}
    for r in report.results:
        line_results.setdefault(r.mutant.line_number, []).append(r)

    surviving_lines = {r.mutant.line_number for r in report.surviving_mutants}

    lines_html: list[str] = []
    for i, raw_line in enumerate(source_text.splitlines(), 1):
        escaped = html.escape(raw_line) if raw_line else "&nbsp;"

        line_class = ""
        tooltip    = ""

        if i in line_results:
            relevant = [
                r for r in line_results[i]
                if r.mutant.id not in report.equivalent_flags
            ]
            if relevant:
                if i in surviving_lines:
                    line_class = "survived"
                    tip_rows = "".join(
                        f'<tr class="tip-{r.status.name.lower()}">'
                        f'<td>{html.escape(r.mutant.id)}</td>'
                        f'<td>{html.escape(r.mutant.original_node)}'
                        f' -> {html.escape(r.mutant.mutated_node)}</td>'
                        f'<td>{r.status.name}</td></tr>'
                        for r in relevant
                    )
                    tooltip = f'<div class="tip"><table>{tip_rows}</table></div>'
                else:
                    line_class = "killed"

        lines_html.append(
            f'<div class="src-line {line_class}">'
            f'<span class="ln">{i:>4}</span>'
            f'<span class="src">{escaped}</span>'
            f'{tooltip}'
            f'</div>'
        )

    return f"""
    <section class="card src-card">
      <h2>Source: {html.escape(report.source_file)}</h2>
      <p class="muted legend">
        <span class="pill survived">survived</span> mutant survived on this line &nbsp;
        <span class="pill killed">killed</span> all mutants killed &nbsp;
        Hover survived lines to see mutations.
      </p>
      <div class="src-view">{"".join(lines_html)}</div>
    </section>"""


# ------ HTML template ------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>MutaGuard -- {{TITLE}}</title>
<style>
  :root {
    --bg: #0f1117; --surface: #1a1d27; --border: #2d3148;
    --text: #e2e8f0; --muted: #718096;
    --green: #48bb78; --red: #fc8181; --yellow: #f6e05e; --blue: #63b3ed;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { background: var(--bg); color: var(--text);
         font-family: 'Segoe UI', system-ui, sans-serif;
         font-size: 14px; line-height: 1.6; }
  h1 { padding: 1.2rem 2rem; background: var(--surface);
       border-bottom: 1px solid var(--border);
       font-size: 1.3rem; color: var(--blue); }
  h2 { font-size: 0.95rem; font-weight: 600; color: var(--blue);
       margin-bottom: 1rem; }
  .container { max-width: 1200px; margin: 0 auto;
               padding: 1.5rem; display: flex;
               flex-direction: column; gap: 1.5rem; }
  .card { background: var(--surface); border: 1px solid var(--border);
          border-radius: 8px; padding: 1.5rem; }
  .src-card { padding: 1rem; }
  .summary { display: flex; flex-direction: column; }
  .score { font-size: 3rem; font-weight: 800; line-height: 1;
           margin-bottom: 0.2rem; }
  .score.good { color: var(--green); }
  .score.warn { color: var(--yellow); }
  .score.bad  { color: var(--red); }
  .score-label { color: var(--muted); margin-bottom: 1rem; font-size: 12px; }
  .stat-table td { padding: 0.15rem 0.75rem 0.15rem 0; }
  .muted { color: var(--muted); font-size: 12px; margin-bottom: 0.75rem; }
  .num { text-align: right; font-variant-numeric: tabular-nums;
         font-weight: 600; }
  .num.killed   { color: var(--green); }
  .num.survived { color: var(--red); }
  .num.timeout  { color: var(--yellow); }
  .num.equiv    { color: var(--muted); }
  .breakdown-table { width: 100%; border-collapse: collapse; font-size: 13px; }
  .breakdown-table th { text-align: left; padding: 0.4rem 0.75rem;
                        border-bottom: 1px solid var(--border);
                        color: var(--muted); font-weight: 500; }
  .breakdown-table td { padding: 0.3rem 0.75rem;
                        border-bottom: 1px solid var(--border); }
  .breakdown-table tr:last-child td { border-bottom: none; }
  code { background: rgba(255,255,255,0.08); padding: 1px 5px;
         border-radius: 3px;
         font-family: 'Cascadia Code', 'Consolas', monospace;
         font-size: 12px; }
  .legend { margin-bottom: 0.75rem; }
  .pill { display: inline-block; padding: 1px 8px; border-radius: 12px;
          font-size: 11px; font-weight: 600; }
  .pill.survived { background: #2d1a1a; color: var(--red); }
  .pill.killed   { background: #1a2e1a; color: var(--green); }
  .src-view { font-family: 'Cascadia Code', 'Consolas', monospace;
              font-size: 12px; line-height: 1.5; overflow-x: auto;
              background: #0d0f18; border-radius: 6px; padding: 0.5rem 0; }
  .src-line { display: flex; padding: 0 0.75rem; position: relative;
              white-space: pre; }
  .src-line:hover { background: rgba(255,255,255,0.03); }
  .src-line.killed   { background: #1a2e1a; }
  .src-line.survived { background: #2d1a1a; cursor: pointer; }
  .src-line.survived .src::after { content: '  <-- survived';
                                   color: var(--red); font-size: 10px; }
  .ln { color: var(--muted); user-select: none; min-width: 3rem;
        text-align: right; margin-right: 1.5rem; flex-shrink: 0; }
  .tip { display: none; position: absolute; left: 4rem; top: 100%;
         z-index: 100; background: #252836;
         border: 1px solid var(--border); border-radius: 6px;
         padding: 0.5rem; min-width: 400px;
         box-shadow: 0 8px 24px rgba(0,0,0,0.5); }
  .src-line.survived:hover .tip { display: block; }
  .tip table { width: 100%; border-collapse: collapse; font-size: 12px; }
  .tip td { padding: 0.2rem 0.4rem;
            border-bottom: 1px solid var(--border); }
  .tip tr:last-child td { border-bottom: none; }
  .tip-survived td { color: var(--red); }
  .tip-killed   td { color: var(--green); }
  .tip-timeout  td { color: var(--yellow); }
</style>
</head>
<body>
<h1>MutaGuard -- {{TITLE}}</h1>
<div class="container">
{{BODY}}
</div>
</body>
</html>"""


