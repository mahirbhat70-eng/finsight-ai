"""PDF parser (Playbook P3.2) — pdfplumber page by page with page-level
provenance; Camelot lattice fallback (guarded import) for bordered tables.

Handles the real-world traps the playbook calls out: merged cells, "Rs in
crore" headers, Indian digit grouping, parenthesized negatives, unicode
minus, dashes as nil.
"""

import re
from dataclasses import dataclass, field

import pdfplumber

NIL_TOKENS = {"-", "--", "—", "–", "nil", "na", "n.a.", "*", ""}
NUM_RE = re.compile(r"[()]|-|[\d.,]+")

STATEMENT_KEYWORDS = {
    "pl": ("statement of profit and loss", "profit and loss", "income statement",
           "p&l", "statement of profit"),
    "bs": ("balance sheet", "statement of assets and liabilities",
           "financial position"),
    "cf": ("cash flows", "cash flow statement"),
}

UNIT_PATTERNS: list[tuple[str, float]] = [
    (r"(?:rs\.?|inr|₹)\s*(?:in\s+)?(?:crore|crores|cr\.?)\b", 1.0),
    (r"(?:rs\.?|inr|₹)\s*(?:in\s+)?(?:lakh|lakhs|lac|lacs)\b", 0.01),
    (r"(?:rs\.?|inr|₹)\s*(?:in\s+)?(?:million|mn|mn\.)\b", 0.1),
    (r"(?:usd|\$)\s*(?:in\s+)?(?:million|mn)\b", 10.0),  # ~ USD mn -> INR cr proxy
]


@dataclass
class ParsedTable:
    page_no: int
    rows: list[list[str]]
    periods: list[str] = field(default_factory=list)
    unit_scale: float = 1.0
    statement_type: str | None = None


@dataclass
class ParsedPage:
    page_no: int
    text: str
    tables: list[list[list[str]]]
    statement_scores: dict[str, int] = field(default_factory=dict)
    unit_scale: float | None = None


@dataclass
class ParsedDoc:
    path: str
    pages: list[ParsedPage]
    tables: list[ParsedTable]

    @property
    def statement_tables(self) -> list[ParsedTable]:
        return [t for t in self.tables if t.statement_type]


def parse_number(raw: str | None) -> float | None:
    """'1,234.56' -> 1234.56; '(45.2)' -> -45.2; '-' -> None (nil);
    '12,34,567' (Indian grouping) -> 1234567 (commas stripped)."""
    if raw is None:
        return None
    token = raw.strip().replace("\u2212", "-").replace("−", "-")
    if token.lower() in NIL_TOKENS:
        return None
    negative = token.startswith("(") and token.endswith(")")
    if negative:
        token = token[1:-1]
    cleaned = token.replace("₹", "").replace("Rs", "").replace("rs", "")
    cleaned = re.sub(r"[a-zA-Z%\s]", "", cleaned).lstrip("$").strip()
    if not cleaned or cleaned in {"-", "."}:
        return None
    try:
        value = float(cleaned.replace(",", ""))
    except ValueError:
        return None
    return -value if negative else value


def parse_period(cell: str) -> str | None:
    """'FY2024' / 'FY 2024-25' / '2023-24' / 'Year ended March 2023' -> FY2024.

    Indian convention: FY 2024-25 ends March 2025, so the END year wins.
    """
    match = re.search(r"fy\s*(\d{4})\s*[-–]\s*(\d{2,4})", cell, re.IGNORECASE)
    if match:
        end = match.group(2)
        end_year = int(end) if len(end) == 4 else 2000 + int(end)
        return f"FY{end_year}"
    match = re.search(r"fy\s*(\d{4})", cell, re.IGNORECASE)
    if match:
        return f"FY{match.group(1)}"
    match = re.search(r"(20\d{2})\s*[-–]\s*(\d{2,4})", cell)
    if match:
        end = match.group(2)
        end_year = int(end) if len(end) == 4 else 2000 + int(end)
        return f"FY{end_year}"
    match = re.search(r"(?:march|mar)\s*,?\s*(20\d{2})", cell, re.IGNORECASE)
    if match:
        return f"FY{match.group(1)}"
    return None


def detect_statement_type(text: str) -> dict[str, int]:
    scores = {}
    lowered = text.lower()
    for stype, keywords in STATEMENT_KEYWORDS.items():
        scores[stype] = sum(lowered.count(k) for k in keywords)
    return scores


def infer_unit_scale(text: str) -> float | None:
    for pattern, scale in UNIT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return scale
    return None


def parse_pdf(path: str) -> ParsedDoc:
    pages: list[ParsedPage] = []
    tables: list[ParsedTable] = []

    with pdfplumber.open(path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            text = page.extract_text() or ""
            scores = detect_statement_type(text)
            unit = infer_unit_scale(text)
            ppage = ParsedPage(page_no=page_no, text=text, tables=[],
                               statement_scores=scores, unit_scale=unit)

            for table in page.extract_tables():
                rows = [[(cell or "").strip() for cell in row]
                        for row in table if row and any(c and c.strip() for c in row)]
                if not rows:
                    continue
                ppage.tables.append(rows)
                header = rows[0]
                periods = [parse_period(cell) for cell in header[1:]]
                tables.append(ParsedTable(
                    page_no=page_no, rows=rows,
                    periods=[p for p in periods if p],
                    unit_scale=unit or 1.0,
                    statement_type=_best_statement_type(scores),
                ))

            # Camelot lattice fallback for bordered tables pdfplumber missed
            if not ppage.tables and any(scores.values()):
                camelot_rows = _camelot_fallback(path, page_no)
                if camelot_rows:
                    header = camelot_rows[0]
                    periods = [parse_period(cell) for cell in header[1:]]
                    tables.append(ParsedTable(
                        page_no=page_no, rows=camelot_rows,
                        periods=[p for p in periods if p],
                        unit_scale=unit or 1.0,
                        statement_type=_best_statement_type(scores),
                    ))
            pages.append(ppage)

    return ParsedDoc(path=path, pages=pages, tables=tables)


def _best_statement_type(scores: dict[str, int]) -> str | None:
    best, best_score = None, 0
    for stype, score in scores.items():
        if score > best_score:
            best, best_score = stype, score
    return best if best_score >= 1 else None


def _camelot_fallback(path: str, page_no: int) -> list[list[str]] | None:
    """Camelot lattice mode; returns None if camelot/ghostscript unavailable."""
    try:
        import camelot  # optional dependency

        tables = camelot.read_pdf(path, pages=str(page_no), flavor="lattice")
        if not tables:
            return None
        return [[[cell or "" for cell in row] for row in t.df.values.tolist()]
                for t in tables][0]
    except Exception:  # noqa: BLE001 — optional dependency
        return None


def serialize_table_for_chunks(table: ParsedTable) -> str:
    """Tables serialized as 'label: v1 | v2 | ...' lines, kept intact."""
    lines = []
    for row in table.rows[1:]:
        label = row[0] if row else ""
        values = " | ".join(c for c in row[1:] if c)
        if label:
            lines.append(f"{label}: {values}")
    return "\n".join(lines)
