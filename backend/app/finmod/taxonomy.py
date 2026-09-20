"""Canonical taxonomy — the platform's spine (Playbook Phase 1, P1.1).

A mini-XBRL: every extracted or seeded value maps to exactly one canonical
key. Labels differ across filings ("Revenue from Operations" vs "Revenues");
keys never do. This is the precondition for benchmarking and for the
deterministic engine.
"""

from dataclasses import dataclass

from rapidfuzz import fuzz

STATEMENT_TYPES = ("pl", "bs", "cf")
UNIT_INR_CR = "INR_cr"
UNIT_MN_SHARES = "mn_shares"


@dataclass(frozen=True)
class CanonicalItem:
    key: str
    label: str
    statement_type: str  # pl | bs | cf
    unit_hint: str
    aliases: tuple[str, ...] = ()
    derived: bool = False


ITEMS: tuple[CanonicalItem, ...] = (
    # --- Profit & loss (duration, INR crore) ---
    CanonicalItem("revenue", "Revenue", "pl", UNIT_INR_CR,
                  ("revenue from operations", "total revenue", "net sales", "revenues",
                   "revenue from operation", "sales", "total revenue from operations")),
    CanonicalItem("cogs", "Cost of Goods Sold", "pl", UNIT_INR_CR,
                  ("cost of materials consumed", "cost of sales", "cost of revenue",
                   "cost of goods sold", "purchases", "cost of materials")),
    CanonicalItem("gross_profit", "Gross Profit", "pl", UNIT_INR_CR, ("gross profit",)),
    CanonicalItem("opex", "Operating Expenses", "pl", UNIT_INR_CR,
                  ("operating expenses", "total operating expenses", "total expenditure",
                   "sg&a", "selling general and administrative expenses")),
    CanonicalItem("ebitda", "EBITDA", "pl", UNIT_INR_CR,
                  ("ebitda", "operating profit before depreciation",
                   "profit before interest tax and depreciation", "pbdit",
                   "operating profit (before depreciation and amortisation)")),
    CanonicalItem("dna", "Depreciation & Amortisation", "pl", UNIT_INR_CR,
                  ("depreciation and amortisation", "depreciation",
                   "depreciation and amortization", "depreciation & amortization expense")),
    CanonicalItem("ebit", "EBIT", "pl", UNIT_INR_CR,
                  ("ebit", "operating profit", "profit from operations",
                   "operating profit after depreciation")),
    CanonicalItem("interest_expense", "Interest Expense", "pl", UNIT_INR_CR,
                  ("finance costs", "finance cost", "interest expense",
                   "interest and finance costs")),
    CanonicalItem("other_income", "Other Income", "pl", UNIT_INR_CR,
                  ("other income", "other operating income")),
    CanonicalItem("pbt", "Profit Before Tax", "pl", UNIT_INR_CR,
                  ("profit before tax", "profit before taxation", "pbt",
                   "earnings before taxes")),
    CanonicalItem("tax_expense", "Tax Expense", "pl", UNIT_INR_CR,
                  ("tax expense", "total tax expense", "income tax expense", "current tax")),
    CanonicalItem("pat", "Profit After Tax", "pl", UNIT_INR_CR,
                  ("pat", "net profit", "profit after tax", "net income",
                   "profit for the year", "net profit (loss) for the period")),
    # --- Balance sheet (instant, INR crore) ---
    CanonicalItem("cash", "Cash & Cash Equivalents", "bs", UNIT_INR_CR,
                  ("cash and cash equivalents", "cash and bank balances",
                   "cash & bank balances", "cash and cash equivalents at end")),
    CanonicalItem("trade_receivables", "Trade Receivables", "bs", UNIT_INR_CR,
                  ("trade receivables", "sundry debtors", "accounts receivable",
                   "receivables")),
    CanonicalItem("inventory", "Inventory", "bs", UNIT_INR_CR,
                  ("inventories", "inventory", "stock in trade", "stock-in-trade")),
    CanonicalItem("current_assets", "Total Current Assets", "bs", UNIT_INR_CR,
                  ("total current assets", "current assets")),
    CanonicalItem("trade_payables", "Trade Payables", "bs", UNIT_INR_CR,
                  ("trade payables", "sundry creditors", "accounts payable", "payables")),
    CanonicalItem("current_liabilities", "Total Current Liabilities", "bs", UNIT_INR_CR,
                  ("total current liabilities", "current liabilities")),
    CanonicalItem("st_borrowings", "Short-term Borrowings", "bs", UNIT_INR_CR,
                  ("short term borrowings", "current borrowings", "short term debt",
                   "short term loans")),
    CanonicalItem("lt_debt", "Long-term Debt", "bs", UNIT_INR_CR,
                  ("long term borrowings", "non current borrowings", "long term debt",
                   "long-term borrowings")),
    CanonicalItem("total_debt", "Total Debt", "bs", UNIT_INR_CR,
                  ("total debt", "total borrowings", "gross debt")),
    CanonicalItem("total_equity", "Total Equity", "bs", UNIT_INR_CR,
                  ("total equity", "total shareholders funds", "net worth",
                   "shareholders funds", "total stockholders equity",
                   "total share capital and reserves")),
    # --- Per-share (mn shares) ---
    CanonicalItem("shares_outstanding", "Shares Outstanding", "pl", UNIT_MN_SHARES,
                  ("shares outstanding", "number of shares",
                   "diluted shares outstanding", "equity shares outstanding")),
    # --- Cash flow (duration, INR crore) ---
    CanonicalItem("ocf", "Operating Cash Flow", "cf", UNIT_INR_CR,
                  ("net cash from operating activities", "cash from operations",
                   "operating cash flow", "net cash generated from operations")),
    CanonicalItem("capex", "Capital Expenditure", "cf", UNIT_INR_CR,
                  ("capital expenditure", "purchase of property plant and equipment",
                   "purchase of fixed assets", "additions to fixed assets",
                   "payments for acquisition of fixed assets")),
    CanonicalItem("fcf", "Free Cash Flow", "cf", UNIT_INR_CR,
                  ("free cash flow", "fcf"), derived=True),
)

REGISTRY: dict[str, CanonicalItem] = {item.key: item for item in ITEMS}
ALL_KEYS: tuple[str, ...] = tuple(REGISTRY)

# Exact (normalized) label -> key lookup, built from aliases + labels + keys.
_ALIAS_INDEX: dict[str, str] = {}
for _item in ITEMS:
    for _lab in ( _item.key, _item.label, *_item.aliases ):
        _norm = " ".join(str(_lab).lower().replace("&", " and ").replace("-", " ").split())
        _ALIAS_INDEX.setdefault(_norm, _item.key)


def normalize_label(raw: str) -> str:
    return " ".join(raw.lower().replace("&", " and ").replace("-", " ").split()).strip(" .:;*")


def get(key: str) -> CanonicalItem:
    return REGISTRY[key]


def resolve_label(raw_label: str, min_score: float = 92.0) -> tuple[str | None, float]:
    """Resolve a raw filing label to a canonical key.

    Exact (normalized) alias match -> confidence 1.0.
    Fuzzy match -> token-set similarity with a coverage penalty, so compound
    labels like "Provisions and Other Current Liabilities" do NOT auto-resolve
    to "Total Current Liabilities". Prefix-anchored labels (canonical alias
    followed by qualifiers/units, e.g. "Trade Receivables (Sundry Debtors)"
    or "Shares Outstanding (mn)") keep full token-set confidence.
    No match at min_score -> (None, 0.0) — the label goes to the review queue.
    """
    norm = normalize_label(raw_label)
    if not norm:
        return None, 0.0
    if norm in _ALIAS_INDEX:
        return _ALIAS_INDEX[norm], 1.0
    best_key, best_score = None, 0.0
    for alias, key in _ALIAS_INDEX.items():
        tsr = fuzz.token_set_ratio(norm, alias) / 100.0
        # Penalise unexplained tokens: how much of the longer string does the
        # shorter one actually cover?
        coverage = min(len(norm), len(alias)) / max(len(norm), len(alias))
        score = tsr * (0.55 + 0.45 * coverage)
        if norm.startswith(alias) or alias.startswith(norm):
            # Anchored match: alias + qualifier/unit suffix — trust it fully.
            score = max(score, tsr)
        if score > best_score:
            best_key, best_score = key, score
    if best_key is not None and best_score * 100.0 >= min_score:
        return best_key, min(best_score, 1.0)
    return None, 0.0


# Identity rules used for cross-checks and derived auto-fill (mapper, Phase 3).
DERIVED_RULES: dict[str, tuple[str, ...]] = {
    # key: (formula template tokens) — implemented in ingestion.mapper
    "gross_profit": ("revenue", "-", "cogs"),
    "opex": ("gross_profit", "-", "ebitda"),
    "ebitda": ("gross_profit", "-", "opex"),
    "ebit": ("ebitda", "-", "dna"),
    "pbt": ("ebit", "-", "interest_expense", "+", "other_income"),
    "pat": ("pbt", "-", "tax_expense"),
    "total_debt": ("lt_debt", "+", "st_borrowings"),
    "fcf": ("ocf", "-", "capex"),
}


def validate_keys() -> list[str]:
    """Return a list of registry problems (empty list = healthy)."""
    problems: list[str] = []
    keys = [item.key for item in ITEMS]
    if len(keys) != len(set(keys)):
        problems.append("duplicate keys in registry")
    for item in ITEMS:
        if item.statement_type not in STATEMENT_TYPES:
            problems.append(f"{item.key}: bad statement_type {item.statement_type}")
        if not item.aliases:
            problems.append(f"{item.key}: no aliases")
        for token in DERIVED_RULES.get(item.key, ()):
            if token not in ("+", "-") and token not in REGISTRY:
                problems.append(f"{item.key}: derived rule references unknown key {token}")
    return problems
