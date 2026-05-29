"""Render a HealthReport as a terminal panel or a self-contained HTML page.

The terminal view is for at-a-glance operation; the HTML export (no external
assets, no JS deps) is for sharing a snapshot or pinning in a browser tab. Both
are pure presentation over ``HealthReport`` — no recomputation, no I/O surprises.
"""

from __future__ import annotations

import html

from ..metrics import calibration_bins
from .health import AlertLevel, HealthReport


def _sparkline(values: list[float], width: int = 40) -> str:
    """ASCII sparkline of an equity curve, downsampled to `width` columns."""
    blocks = "▁▂▃▄▅▆▇█"
    if len(values) < 2:
        return ""
    # Downsample by averaging buckets so long runs still fit.
    n = len(values)
    cols = min(width, n)
    bucket = n / cols
    sampled = [
        sum(values[int(i * bucket):max(int((i + 1) * bucket), int(i * bucket) + 1)])
        / max(1, len(values[int(i * bucket):max(int((i + 1) * bucket), int(i * bucket) + 1)]))
        for i in range(cols)
    ]
    lo, hi = min(sampled), max(sampled)
    if hi == lo:
        return blocks[0] * cols
    return "".join(
        blocks[min(len(blocks) - 1, int((v - lo) / (hi - lo) * (len(blocks) - 1)))]
        for v in sampled
    )


_LEVEL_GLYPH = {
    AlertLevel.OK: "✅",
    AlertLevel.INFO: "ℹ️ ",
    AlertLevel.WARN: "⚠️ ",
    AlertLevel.CRITICAL: "🛑",
}


def render_terminal(report: HealthReport) -> str:
    r = report
    status = r.status

    def brier_line(label: str, model: float, market: float, beats: bool) -> str:
        verdict = "beats market ✅" if beats else "trails market ✗"
        return f"  {label:<14}: model {model:.4f} | market {market:.4f}  → {verdict}"

    lines = [
        "═══════════════ polybet — ops dashboard ═══════════════",
        f"  STATUS          : {_LEVEL_GLYPH[status]} {status.label}",
        "",
        "  ── P&L ──────────────────────────────────────────────",
        f"  bets / resolved : {r.n_bets} / {r.n_resolved}",
        f"  start equity    : ${r.start_equity:,.2f}",
        f"  current equity  : ${r.equity:,.2f}  ({r.realized_pnl:+,.2f})",
        f"  equity curve    : {_sparkline(r.equity_curve)}",
        "",
        "  ── Risk ─────────────────────────────────────────────",
        f"  drawdown        : {r.drawdown:.1%}  (worst {r.max_drawdown:.1%})",
        f"  kill-switch     : {r.kill_switch:.0%}  "
        + ("🛑 ENGAGED" if r.kill_switch_engaged else "armed"),
        "",
        "  ── Calibration (lower Brier = better) ───────────────",
        brier_line("all-time", r.brier_model_all, r.brier_market_all, r.beats_baseline_all),
    ]
    if r.brier_model_recent == r.brier_model_recent:  # not NaN
        lines.append(
            brier_line("recent", r.brier_model_recent, r.brier_market_recent, r.beats_baseline_recent)
        )
    lines += ["", "  ── Alerts ───────────────────────────────────────────"]
    for a in r.alerts:
        lines.append(f"  {_LEVEL_GLYPH[a.level]} [{a.level.label}] {a.message}")
    lines.append("══════════════════════════════════════════════════════")
    return "\n".join(lines)


def render_html(
    report: HealthReport,
    predictions: list[float] | None = None,
    outcomes: list[int] | None = None,
    title: str = "polybet — ops dashboard",
) -> str:
    """A single self-contained HTML file (inline CSS, no JS, no external assets).

    If forecast/outcome pairs are supplied, a reliability diagram (calibration
    table) is included — the clearest single picture of whether we have edge.
    """
    r = report
    status = r.status
    status_color = {
        AlertLevel.OK: "#1a7f37",
        AlertLevel.INFO: "#0969da",
        AlertLevel.WARN: "#9a6700",
        AlertLevel.CRITICAL: "#cf222e",
    }[status]

    def esc(x: object) -> str:
        return html.escape(str(x))

    def metric(label: str, value: str, sub: str = "") -> str:
        sub_html = f'<div class="sub">{esc(sub)}</div>' if sub else ""
        return (
            f'<div class="card"><div class="label">{esc(label)}</div>'
            f'<div class="value">{esc(value)}</div>{sub_html}</div>'
        )

    cards = [
        metric("Status", status.label),
        metric("Equity", f"${r.equity:,.2f}", f"{r.realized_pnl:+,.2f} realized"),
        metric("Bets / resolved", f"{r.n_bets} / {r.n_resolved}"),
        metric("Drawdown", f"{r.drawdown:.1%}", f"worst {r.max_drawdown:.1%}"),
        metric(
            "Kill-switch",
            f"{r.kill_switch:.0%}",
            "ENGAGED" if r.kill_switch_engaged else "armed",
        ),
        metric(
            "Brier (all-time)",
            f"{r.brier_model_all:.4f}",
            f"market {r.brier_market_all:.4f} · "
            + ("edge ✓" if r.beats_baseline_all else "no edge"),
        ),
    ]
    if r.brier_model_recent == r.brier_model_recent:
        cards.append(
            metric(
                "Brier (recent)",
                f"{r.brier_model_recent:.4f}",
                f"market {r.brier_market_recent:.4f} · "
                + ("edge ✓" if r.beats_baseline_recent else "trailing"),
            )
        )

    alert_rows = "".join(
        f'<tr class="lvl-{a.level.label.lower()}"><td>{a.level.label}</td>'
        f"<td>{esc(a.code)}</td><td>{esc(a.message)}</td></tr>"
        for a in r.alerts
    )

    calibration_html = ""
    if predictions and outcomes:
        bins = calibration_bins(predictions, outcomes, n_bins=10)
        rows = ""
        for b in bins:
            if b.count == 0:
                continue
            # Bar width encodes population; the closer avg_pred and observed, the
            # better calibrated. We show both for a textual reliability diagram.
            err = abs(b.avg_prediction - b.observed_rate)
            bar = int(b.observed_rate * 100)
            rows += (
                f"<tr><td>{b.lo:.1f}–{b.hi:.1f}</td><td>{b.count}</td>"
                f"<td>{b.avg_prediction:.3f}</td><td>{b.observed_rate:.3f}</td>"
                f'<td><div class="bar" style="width:{bar}%"></div></td>'
                f'<td>{err:.3f}</td></tr>'
            )
        calibration_html = f"""
        <h2>Reliability diagram</h2>
        <p class="muted">Well-calibrated means predicted ≈ observed in every bucket.</p>
        <table class="cal">
          <tr><th>bucket</th><th>n</th><th>avg pred</th><th>observed</th>
              <th>observed rate</th><th>|error|</th></tr>
          {rows}
        </table>"""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>
  :root {{ color-scheme: light dark; }}
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
         background: #f6f8fa; color: #1f2328; }}
  header {{ background: {status_color}; color: #fff; padding: 20px 28px; }}
  header h1 {{ margin: 0; font-size: 20px; }}
  header .status {{ font-size: 14px; opacity: .92; margin-top: 4px; }}
  main {{ padding: 24px 28px; max-width: 1000px; margin: 0 auto; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr));
           gap: 14px; }}
  .card {{ background: #fff; border: 1px solid #d0d7de; border-radius: 10px;
           padding: 14px 16px; }}
  .card .label {{ font-size: 12px; color: #656d76; text-transform: uppercase;
                  letter-spacing: .04em; }}
  .card .value {{ font-size: 24px; font-weight: 650; margin-top: 4px; }}
  .card .sub {{ font-size: 12px; color: #656d76; margin-top: 2px; }}
  h2 {{ margin-top: 30px; font-size: 16px; }}
  .muted {{ color: #656d76; font-size: 13px; }}
  table {{ border-collapse: collapse; width: 100%; background: #fff;
           border: 1px solid #d0d7de; border-radius: 10px; overflow: hidden; }}
  th, td {{ text-align: left; padding: 8px 12px; border-bottom: 1px solid #eaeef2;
            font-size: 13px; }}
  th {{ background: #f6f8fa; color: #656d76; font-weight: 600; }}
  .bar {{ background: {status_color}; height: 12px; border-radius: 3px; min-width: 2px; }}
  tr.lvl-critical td {{ color: #cf222e; font-weight: 600; }}
  tr.lvl-warn td {{ color: #9a6700; }}
  tr.lvl-ok td {{ color: #1a7f37; }}
</style></head>
<body>
<header><h1>{esc(title)}</h1>
<div class="status">{status.label} · {r.n_resolved} resolved · {r.n_bets} bets</div></header>
<main>
  <div class="grid">{''.join(cards)}</div>
  <h2>Alerts</h2>
  <table><tr><th>level</th><th>code</th><th>message</th></tr>{alert_rows}</table>
  {calibration_html}
  <p class="muted" style="margin-top:24px">
    Generated by polybet monitoring. Synthetic/paper data unless wired to a live
    signal — calibration here proves the pipeline, not real-world edge.</p>
</main></body></html>"""
