"""Synthetic NovaTech annual report PDF + ground truth (Playbook P1.4).

Every number is rendered from the articulated model, so the ground truth is
exact. The document is byte-stable (ReportLab invariant=1, same seed -> same
bytes). Labels deliberately use Indian-filing phrasing so the Phase 3 parser
+ mapper exercise realistic alias resolution; two rows are ambiguous on
purpose to drive the review-queue demo (P3.4).

Output:
- data/fixtures/novatech_annual_report.pdf   (60+ pages incl. filler)
- page registry -> part of novatech_ground_truth.json
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Flowable,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus.tableofcontents import TableOfContents

from novatech_model import build_model

INK = colors.HexColor("#1a1a2e")
ACCENT = colors.HexColor("#4338ca")
GREY = colors.HexColor("#6b7280")

P_AND_L_ROWS = [  # (display label, canonical key or None for noise rows)
    ("Revenue from Operations", "revenue"),
    ("Cost of Materials Consumed", "cogs"),
    ("Gross Profit", "gross_profit"),
    ("Total Operating Expenses", "opex"),
    ("Operating Profit (Before Depreciation and Amortisation)", "ebitda"),
    ("Depreciation and Amortisation", "dna"),
    ("Operating Profit", "ebit"),
    ("Finance Costs", "interest_expense"),
    ("Other Income", "other_income"),
    ("Expenditure on Research and Development", "rd_noise"),  # ambiguous on purpose
    ("Profit Before Tax", "pbt"),
    ("Total Tax Expense", "tax_expense"),
    ("Profit After Tax", "pat"),
    ("Shares Outstanding (mn)", "shares_outstanding"),
]

BS_ROWS = [
    ("Cash and Cash Equivalents", "cash"),
    ("Trade Receivables (Sundry Debtors)", "trade_receivables"),
    ("Inventories", "inventory"),
    ("Total Current Assets", "current_assets"),
    ("Trade Payables (Sundry Creditors)", "trade_payables"),
    ("Provisions and Contingencies (Net)", "provisions_noise"),  # ambiguous
    ("Total Current Liabilities", "current_liabilities"),
    ("Short Term Borrowings", "st_borrowings"),
    ("Long Term Borrowings", "lt_debt"),
    ("Total Debt", "total_debt"),
    ("Total Shareholders Funds", "total_equity"),
]

CF_ROWS = [
    ("Net Cash from Operating Activities", "ocf"),
    ("Purchase of Fixed Assets (Capex)", "capex"),
    ("Free Cash Flow", "fcf"),
]


class PageMarker(Flowable):
    """Zero-size flowable that records the page it lands on."""

    def __init__(self, registry: dict, key: str) -> None:
        super().__init__()
        self.registry = registry
        self.key = key

    def wrap(self, _w, _h):
        return 0, 0

    def draw(self):
        self.registry[self.key] = self.canv.getPageNumber()


class SectionHeading(Paragraph):
    """Heading that also feeds the TableOfContents."""

    def __init__(self, text: str, level: int = 0) -> None:
        styles = _styles()
        style = styles["SectionH1"] if level == 0 else styles["SectionH2"]
        super().__init__(text, style)
        self.toc_text = text
        self.level = level


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "SectionH1": ParagraphStyle(
            "SectionH1", parent=base["Heading1"], fontName="Helvetica-Bold",
            fontSize=16, textColor=INK, spaceBefore=14, spaceAfter=8),
        "SectionH2": ParagraphStyle(
            "SectionH2", parent=base["Heading2"], fontName="Helvetica-Bold",
            fontSize=12, textColor=ACCENT, spaceBefore=10, spaceAfter=6),
        "Body": ParagraphStyle(
            "Body", parent=base["BodyText"], fontName="Helvetica",
            fontSize=10, leading=14, spaceAfter=8),
        "Cover": ParagraphStyle(
            "Cover", parent=base["Title"], fontName="Helvetica-Bold",
            fontSize=28, textColor=INK, alignment=TA_CENTER, spaceAfter=12),
        "Sub": ParagraphStyle(
            "Sub", parent=base["Normal"], fontName="Helvetica",
            fontSize=13, textColor=GREY, alignment=TA_CENTER),
    }


class _Doc(SimpleDocTemplate):
    def afterFlowable(self, flowable) -> None:  # feed the TOC
        if isinstance(flowable, SectionHeading):
            self.notify("TOCEntry", (flowable.level, flowable.toc_text, self.page))


def _fmt(v: float) -> str:
    return f"({abs(v):,.1f})" if v < 0 else f"{v:,.1f}"


def _statement_table(model: dict, rows: list, years_idx: slice | None = None) -> Table:
    periods = model["periods"]
    header = ["Rs in crore"] + list(periods)
    data = [header]
    for label, key in rows:
        values = model["items"].get(key)
        row = [label]
        if values is None:  # deliberate noise/ambiguous row
            noise = _noise_row(label, model)
            row += [_fmt(v) for v in noise]
        else:
            row += [_fmt(v) for v in values]
        data.append(row)
    tbl = Table(data, colWidths=[70 * mm] + [22 * mm] * len(periods))
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8.5),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 8.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("TEXTCOLOR", (0, 0), (-1, 0), ACCENT),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, ACCENT),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tbl


def _noise_row(label: str, model: dict) -> list[float]:
    """Deterministic filler values for deliberately-unmapped rows."""
    rev = model["items"]["revenue"]
    if "research" in label.lower():
        return [0.0085 * r for r in rev]  # ~0.85% of revenue
    return [14.0, 18.5, 23.0, 42.2, 31.5]  # provisions-style small balances


def _mdna_paragraphs(model: dict) -> list[tuple[str, list[str]]]:
    """(period, [paragraphs]) with the real numbers embedded in sentences."""
    out = []
    cfg = model["config"]
    for t, y in enumerate(model["years"]):
        prev_rev = model["openings"][t]["revenue"]
        growth = (y["revenue"] / prev_rev - 1) * 100
        margin = y["ebitda"] / y["revenue"] * 100
        margin_prev = (model["years"][t - 1]["ebitda"] / model["years"][t - 1]["revenue"]
                       * 100) if t else 24.5
        bps = (margin - margin_prev) * 100
        direction = "recovered" if bps > 0 else "contracted"
        p1 = (
            f"Revenue from operations grew {growth:.1f}% to Rs {y['revenue']:,.1f} "
            f"crore in {y['period']}, driven by order book execution in "
            f"{cfg.narrative['sector']}. EBITDA stood at Rs {y['ebitda']:,.1f} "
            f"crore, a margin of {margin:.1f}%. The EBITDA margin {direction} "
            f"{abs(bps):,.0f} bps versus the prior year, driven by input cost "
            f"inflation, product mix and operating leverage at the new plants. "
            f"Profit after tax was Rs {y['pat']:,.1f} crore."
        )
        if y["period"] == "FY2024":
            p2 = (
                f"The Board approved a Rs {y['capex']:,.1f} crore "
                f"{cfg.narrative['fy24_capex_note']} during the year, funded "
                f"primarily through long-term borrowings. Gross debt accordingly "
                f"rose to Rs {y['total_debt']:,.1f} crore and cash was managed "
                f"down to Rs {y['cash']:,.1f} crore as a deliberate treasury "
                f"decision. Management expects the commissioned capacity to ramp "
                f"through FY2026-27 and restore free cash flow."
            )
        elif y["period"] == "FY2025":
            conc = cfg.customer_a_concentration * 100
            p2 = (
                f"Trade receivables stood at Rs {y['trade_receivables']:,.1f} "
                f"crore ({y['dso']:.0f} days of sales, versus 58 days in FY2021) "
                f"and inventories at Rs {y['inventory']:,.1f} crore "
                f"({y['dio']:.0f} days), against trade payables of Rs "
                f"{y['trade_payables']:,.1f} crore ({y['dpo']:.0f} days). "
                f"Customer concentration remains a monitoring item: Customer A "
                f"represents {conc:.1f}% of revenue. Cash closed the year at Rs "
                f"{y['cash']:,.1f} crore after commissioning debt repayments."
            )
        else:
            p2 = (
                f"Working capital absorbed cash during the year as receivable "
                f"days extended to {y['dso']:.0f} (FY2021: 58). Operating cash "
                f"flow was Rs {y['ocf']:,.1f} crore against EBITDA of Rs "
                f"{y['ebitda']:,.1f} crore. Free cash flow after capital "
                f"expenditure of Rs {y['capex']:,.1f} crore was Rs "
                f"{y['fcf']:,.1f} crore."
            )
        out.append((y["period"], [p1, p2]))
    return out


def build_pdf(output_path: str, model: dict) -> dict:
    """Build the annual report; return the page registry for ground truth."""
    registry: dict = {}
    styles = _styles()
    story: list = []

    # Cover
    story += [
        Spacer(1, 60 * mm),
        Paragraph("NovaTech Industries Ltd", styles["Cover"]),
        Paragraph("Annual Report 2024-25", styles["Sub"]),
        Spacer(1, 8 * mm),
        Paragraph(f"Registered office: Pune, Maharashtra, India", styles["Sub"]),
        Paragraph("Synthetic document generated for platform evaluation", styles["Sub"]),
        Spacer(1, 30 * mm),
        Paragraph("Management Discussion & Analysis | Financial Statements | Notes",
                  styles["Sub"]),
        PageBreak(),
    ]

    # Contents
    story += [SectionHeading("Contents"), TableOfContents(), PageBreak()]

    # MD&A
    story += [SectionHeading("Management Discussion and Analysis")]
    for period, paras in _mdna_paragraphs(model):
        marker = PageMarker(registry, f"mdna_{period.lower()}")
        story += [SectionHeading(f"Performance Review — {period}", level=1),
                  marker]
        for p in paras:
            story += [Paragraph(p, styles["Body"])]
    story += [PageBreak()]

    # Standalone P&L
    story += [SectionHeading("Standalone Financial Statements"),
              SectionHeading("Standalone Statement of Profit and Loss", level=1),
              PageMarker(registry, "standalone_pl"),
              _statement_table(model, P_AND_L_ROWS),
              PageBreak()]

    # Consolidated statements
    story += [SectionHeading("Consolidated Financial Statements")]
    story += [
        SectionHeading("Consolidated Statement of Profit and Loss", level=1),
        PageMarker(registry, "pl"),
        _statement_table(model, P_AND_L_ROWS),
        Spacer(1, 6 * mm),
        SectionHeading("Consolidated Balance Sheet", level=1),
        PageMarker(registry, "bs"),
        _statement_table(model, BS_ROWS),
        Spacer(1, 6 * mm),
        SectionHeading("Consolidated Statement of Cash Flows", level=1),
        PageMarker(registry, "cf"),
        _statement_table(model, CF_ROWS),
        PageBreak(),
    ]

    # Notes
    story += [SectionHeading("Notes to the Financial Statements")]
    story += [
        SectionHeading("Note 1 — Debt Schedule and Obligations", level=1),
        PageMarker(registry, "debt_note"),
        _debt_schedule_table(model),
        Paragraph(
            "The average interest cost across the borrowing book was 9.2% "
            "during the year. Long-term borrowings carry covenants requiring "
            "net debt to EBITDA below 4.0x; as of FY2025 the ratio stands at "
            "2.67x. Material obligations fall due in FY2027 (Rs 890 crore) "
            "and FY2029 (Rs 1,150 crore).", styles["Body"]),
        SectionHeading("Note 2 — Customer Concentration", level=1),
        PageMarker(registry, "concentration"),
        Paragraph(
            f"Customer A represents {model['config'].customer_a_concentration*100:.1f}% "
            "of FY2025 revenue (FY2024: 13.1%; FY2023: 12.4%). The top five "
            "customers together represent 41.8% of revenue. The Company has "
            "entered into multi-year supply agreements with its two largest "
            "customers, which partially mitigates concentration risk.",
            styles["Body"]),
        SectionHeading("Note 3 — Related Party Transactions", level=1),
        PageMarker(registry, "related_party"),
        Paragraph(
            "Related party transactions in the ordinary course of business "
            "include component supplies from NovaTech Components Pvt Ltd (a "
            "subsidiary) amounting to Rs 214.0 crore in FY2025, and managerial "
            "remuneration of Rs 9.6 crore. All transactions are at arm's length "
            "and approved by the Audit Committee.", styles["Body"]),
        PageBreak(),
    ]

    # Risk factors (2 pages)
    story += [SectionHeading("Risk Factors")]
    story += [PageMarker(registry, "risk")]
    for title, body in [
        ("Customer concentration", "Dependence on a small number of large OEM "
         "customers; loss of Customer A would materially affect revenue."),
        ("Input cost volatility", "Copper, steel and semiconductor prices drive "
         "gross margin; the FY2021-FY2023 margin contraction reflects this."),
        ("Working capital intensity", "Receivable days have risen from 58 to 71 "
         "over five years as key customers negotiated longer credit terms."),
        ("Leverage after expansion", "The FY2024 capacity expansion was debt "
         "funded; interest coverage and refinancing risk require monitoring."),
        ("Execution risk", "The new capacity must ramp on schedule to deliver "
         "the margin recovery assumed in management guidance."),
        ("Regulatory and ESG", "Environmental clearances at the new plant and "
         "evolving disclosure requirements under SEBI LODR."),
    ]:
        story += [SectionHeading(title, level=1),
                  Paragraph(body, styles["Body"])]
    story += [PageBreak()]

    # Filler section so the document is a realistic 60+ page corpus
    story += [SectionHeading("Annexures and Shareholder Information")]
    filler = ("This synthetic annexure page contains standard corporate "
              "governance disclosures, board committee composition, and "
              "shareholding patterns. It exists so that retrieval quality is "
              "tested against a realistic document length. ")
    for i in range(1, 105):
        story += [Paragraph(f"{filler}Annexure {i}." if i < 5 else filler,
                            styles["Body"])]
        if i % 2 == 0:
            story += [PageBreak()]

    doc = _Doc(
        output_path, pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm,
        topMargin=18 * mm, bottomMargin=18 * mm,
        title="NovaTech Industries Ltd — Annual Report 2024-25",
        author="FinSight AI (synthetic)",
        invariant=1,  # byte-stable output
    )
    doc.multiBuild(story)
    registry["num_pages"] = doc.page  # last page number == page count
    return registry


def _debt_schedule_table(model: dict) -> Table:
    data = [["Period", "Short Term", "Long Term", "Total Debt"]]
    for y in model["years"]:
        data.append([y["period"], _fmt(y["st_borrowings"]), _fmt(y["lt_debt"]),
                     _fmt(y["total_debt"])])
    tbl = Table(data, colWidths=[30 * mm, 40 * mm, 40 * mm, 40 * mm])
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 9),
        ("FONT", (0, 1), (-1, -1), "Helvetica", 9),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2ff")),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return tbl


def build_ground_truth(model: dict, registry: dict) -> dict:
    """Facts (canonical key x period x page) + 20 golden QA pairs."""
    facts = []
    for rows, stmt, page_key in ((P_AND_L_ROWS, "pl", "pl"),
                                 (BS_ROWS, "bs", "bs"),
                                 (CF_ROWS, "cf", "cf")):
        page = registry[page_key]
        for label, key in rows:
            if key in model["items"]:
                for i, period in enumerate(model["periods"]):
                    facts.append({
                        "key": key, "period": period,
                        "value": round(model["items"][key][i], 2),
                        "unit": "mn_shares" if key == "shares_outstanding" else "INR_cr",
                        "page_no": page, "statement": stmt, "label": label,
                    })
    items = model["items"]
    md = {p.lower(): registry[f"mdna_{p.lower()}"] for p in model["periods"]}
    qa = _qa_pairs(model, registry, md)
    return {
        "company": model["company"],
        "filing": "novatech_annual_report.pdf",
        "facts": facts,
        "qa_pairs": qa,
        "pages": registry,
        "concentration_pct": model["config"].customer_a_concentration * 100,
    }


def _qa_pairs(model: dict, registry: dict, md: dict) -> list[dict]:
    items = model["items"]
    fy = len(model["periods"]) - 1
    metric_q = [
        ("What was NovaTech's revenue in FY2025?", "revenue", fy, registry["pl"]),
        ("What was NovaTech's EBITDA in FY2024?", "ebitda", 3, registry["pl"]),
        ("What was profit after tax in FY2025?", "pat", fy, registry["pl"]),
        ("What was capital expenditure in FY2024?", "capex", 3, registry["cf"]),
        ("What was cash and cash equivalents at the end of FY2025?", "cash", fy,
         registry["bs"]),
        ("What is NovaTech's total debt as of FY2025?", "total_debt", fy,
         registry["bs"]),
        ("What were trade receivables in FY2023?", "trade_receivables", 2,
         registry["bs"]),
        ("What was operating cash flow in FY2025?", "ocf", fy, registry["cf"]),
        ("What was inventory at the end of FY2025?", "inventory", fy,
         registry["bs"]),
        ("What is total shareholders' funds as of FY2025?", "total_equity", fy,
         registry["bs"]),
    ]
    pairs = []
    for question, key, t, page in metric_q:
        pairs.append({
            "question": question,
            "expected_metric": {"key": key, "period": model["periods"][t],
                                "value": round(items[key][t], 2)},
            "expected_pages": [page],
        })
    narrative_q = [
        ("Why did EBITDA margin decline in FY2023?", [md["fy2023"]], "21.6"),
        ("What are the major debt obligations?", [registry["debt_note"]], "9.2"),
        ("What is customer concentration risk at NovaTech?",
         [registry["concentration"]], "14.2"),
        ("What was capex in FY24 and why did it spike?", [md["fy2024"],
         registry["cf"]], "2,140"),
        ("How have receivable days trended?", [md["fy2025"]], "71"),
        ("What are the related party transactions?",
         [registry["related_party"]], "214"),
        ("What risk factors does NovaTech highlight?", [registry["risk"]], None),
        ("What drove FY2025 revenue growth?", [md["fy2025"]], "7,340"),
        ("How is the company funded after the expansion?",
         [registry["debt_note"]], "4,474"),
        ("What happened to cash in FY2024?", [md["fy2024"]], "350"),
    ]
    for question, pages, contains in narrative_q:
        pairs.append({
            "question": question,
            "expected_metric": None,
            "expected_pages": pages,
            "expected_contains": contains,
        })
    return pairs


if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "novatech_annual_report.pdf")
    model = build_model()
    reg = build_pdf(str(out), model)
    print(f"pages: {reg.get('num_pages', '?')}")
    print({k: v for k, v in reg.items() if k != "num_pages"})
