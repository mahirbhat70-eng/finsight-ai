"""PDF investment memo (Playbook P6.4): 6-9 pages, ReportLab platypus.

Cover, company overview, financial performance (tables + matplotlib PNGs),
valuation summary (bridge, scenarios, sensitivity), risk flags, peer
benchmark, methodology + assumptions disclosure, disclaimer footer on
every page.
"""

from datetime import UTC, datetime
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

INK = colors.HexColor("#1a1a2e")
ACCENT = colors.HexColor("#4338ca")
MUTED = colors.HexColor("#6b7280")

SEVERITY_COLORS = {"high": colors.HexColor("#b91c1c"),
                   "medium": colors.HexColor("#b45309"),
                   "info": colors.HexColor("#0369a1")}


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(20 * mm, 12 * mm,
                      "Analytical output for evaluation — not investment advice. "
                      f"FinSight AI | page {doc.page}")
    canvas.restoreState()


def build_memo(output_path: str, report: dict, series: dict, periods: list[str],
               company_name: str, comparison: dict | None = None,
               chart_paths: dict[str, Path] | None = None,
               assumptions_version: str = "api-1") -> str:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=9, leading=13)
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=14, textColor=INK,
                        spaceBefore=10, spaceAfter=6)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=11, textColor=ACCENT,
                        spaceBefore=8, spaceAfter=4)
    cover = ParagraphStyle("Cover", parent=styles["Title"], fontSize=22, textColor=INK,
                           alignment=TA_CENTER, spaceAfter=8)
    sub = ParagraphStyle("Sub", parent=styles["Normal"], fontSize=11, textColor=MUTED,
                         alignment=TA_CENTER)

    bridge = report["dcf"]["bridge"]
    story: list = []

    # Cover
    story += [Spacer(1, 50 * mm), Paragraph(f"Investment Memorandum", cover),
              Paragraph(company_name, cover), Spacer(1, 6 * mm),
              Paragraph("Valuation, risk and peer assessment", sub),
              Paragraph(f"assumptions version {assumptions_version}", sub),
              Paragraph(datetime.now(UTC).strftime("%d %B %Y"), sub),
              PageBreak()]

    # Company overview
    story += [Paragraph("1. Company Overview", h1)]
    latest = lambda k: series[k][-1]  # noqa: E731
    story += [Paragraph(
        f"{company_name} generated revenue of Rs {latest('revenue'):,.0f} crore in "
        f"{periods[-1]} at an EBITDA margin of "
        f"{report['metrics']['ebitda_margin'][periods[-1]]['value']*100:.1f}%. The "
        f"company is levered at net debt / EBITDA of "
        f"{report['metrics']['net_debt_to_ebitda'][periods[-1]]['value']:.2f}x "
        f"following its FY2024 capacity expansion, and generated free cash flow of "
        f"Rs {latest('fcf'):,.0f} crore in {periods[-1]}.", body)]

    # Performance
    story += [Paragraph("2. Financial Performance", h1)]
    if chart_paths and "revenue" in chart_paths:
        story += [Image(str(chart_paths["revenue"]), width=170 * mm, height=78 * mm),
                  Spacer(1, 4 * mm)]
    if chart_paths and "fcf" in chart_paths:
        story += [Image(str(chart_paths["fcf"]), width=170 * mm, height=78 * mm),
                  Spacer(1, 4 * mm),
                  Paragraph("Earnings quality: FCF vs EBITDA — the receivables drag "
                            "and the FY2024 expansion capex are visible in the "
                            "divergence.", body)]

    rows = [["INR crore"] + periods]
    for key in ("revenue", "ebitda", "pat", "ocf", "capex", "fcf", "total_debt",
                "total_equity"):
        label = key.replace("_", " ").title()
        rows.append([label] + [f"{v:,.0f}" if v is not None else "—" for v in series[key]])
    story += [_table(rows, money=True), PageBreak()]

    # Valuation
    story += [Paragraph("3. Valuation Summary", h1)]
    bridge_rows = [
        ("PV of explicit FCFF (5y)", bridge["pv_explicit"]),
        ("PV of terminal value (Gordon)", bridge["pv_terminal_gordon"]),
        ("Enterprise value", bridge["enterprise_value"]),
        ("less: net debt", -bridge["net_debt"]),
        ("Equity value", bridge["equity_value"]),
        ("Per share (INR)", bridge["per_share_inr"]),
    ]
    story += [_table([["DCF bridge (INR crore)", "value"]] +
                     [[k, f"{v:,.1f}"] for k, v in bridge_rows], money=False)]
    story += [Paragraph(
        f"WACC {(report['wacc'] * 100):.2f}% (CAPM cost of equity 14.48%, book "
        f"weights); terminal g {report['dcf']['terminal_growth'] * 100:.1f}%; "
        f"exit-multiple cross-check EV Rs "
        f"{bridge['tv_exit_crosscheck']['ev_exit_method']:,.0f} crore "
        f"({bridge['tv_exit_crosscheck']['spread_vs_gordon']:+.1%} vs Gordon).",
        body)]
    scen_rows = [["Scenario", "Per share (INR)"]]
    for name, s in report["scenarios"].items():
        scen_rows.append([name.title(), f"{s['per_share_inr']:,.2f}"])
    story += [Spacer(1, 4 * mm), _table(scen_rows, money=False)]
    if chart_paths and "sensitivity" in chart_paths:
        story += [Spacer(1, 4 * mm),
                  Image(str(chart_paths["sensitivity"]), width=150 * mm, height=85 * mm)]

    # Risk
    story += [PageBreak(), Paragraph("4. Risk Flags", h1)]
    flag_rows = [["severity", "category", "flag"]]
    for flag in report["risk"]["flags"]:
        flag_rows.append([flag["severity"], flag["category"], flag["rationale"]])
    story += [_table(flag_rows, money=False, severity_col=0)]
    story += [Paragraph(
        f"Composite risk score: {report['risk']['composite_score']}/100.", body)]

    # Peers
    if comparison:
        story += [Paragraph("5. Peer Benchmark", h1)]
        peer_rows = [["metric", "target", "peer median", "percentile"]]
        for row in comparison["metrics"]:
            peer_rows.append([
                row["label"],
                f"{row['target']:.2f}" if row["target"] is not None else "—",
                f"{row['median']:.2f}" if row["median"] is not None else "—",
                f"{row['target_percentile']:.0f}" if row["target_percentile"] is not None else "—",
            ])
        story += [_table(peer_rows, money=False)]
        story += [Paragraph(
            f"Percentile method: {comparison['percentile_method']}. Peer values "
            "are externally provided data, not extracted from filings.", body)]

    # Methodology
    story += [Paragraph("6. Methodology and Assumptions", h1)]
    story += [Paragraph(
        "Deterministic engine: FCFF = EBIT x (1 - tax) + D&A - capex - delta NWC, "
        "discounted at WACC with the mid-year convention ((1+WACC)^(t-0.5)); "
        "terminal value via Gordon growth cross-checked against an exit multiple. "
        "Every number in this memo traces to approved statements or explicit "
        "assumption inputs. The LLM copilot never performs arithmetic; all "
        "computations live in the deterministic finmod engine. No part of this "
        "document is investment advice.", body), PageBreak()]

    doc = SimpleDocTemplate(
        output_path, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=20 * mm,
        title=f"FinSight AI — Investment Memo — {company_name}",
        author="FinSight AI", invariant=1,
    )
    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output_path


def _table(rows: list, money: bool = False, severity_col: int | None = None
           ) -> Table:
    tbl = Table(rows, colWidths=[52 * mm] + [26 * mm] * (len(rows[0]) - 1)
                if len(rows[0]) > 2 else [60 * mm, 100 * mm])
    style = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if severity_col is not None:
        for r in range(1, len(rows)):
            severity = rows[r][severity_col]
            color = SEVERITY_COLORS.get(severity, INK)
            style.append(("TEXTCOLOR", (severity_col, r), (severity_col, r), color))
    tbl.setStyle(TableStyle(style))
    return tbl
