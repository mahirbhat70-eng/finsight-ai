"""SQLAlchemy 2.0 typed models — the full data model (Playbook 2.3).

Conventions:
- Money: Numeric(18,2), unit column carries the scale (INR_cr default).
- Statuses: Python str enums stored as VARCHAR (native_enum=False).
- JSONB where the design says JSONB (postgres dialect).
- chunks.embedding: pgvector Vector(768); tsv: generated tsvector.
"""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.settings import get_settings


def _str_enum(enum_cls: type[Enum]) -> SAEnum:
    """str enum -> VARCHAR column (values are the enum values, not names)."""
    return SAEnum(enum_cls, native_enum=False, length=32,
                  values_callable=lambda c: [e.value for e in c])


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


# --- Enums ---------------------------------------------------------------

class FilingDocType(str, Enum):
    ANNUAL_REPORT = "annual_report"
    DECK = "deck"
    XLSX = "xlsx"


class JobState(str, Enum):
    PENDING = "pending"
    PARSING = "parsing"
    EXTRACTING = "extracting"
    MAPPING = "mapping"
    AWAITING_REVIEW = "awaiting_review"
    EMBEDDING = "embedding"
    READY = "ready"
    FAILED = "failed"


class StatementType(str, Enum):
    PL = "pl"
    BS = "bs"
    CF = "cf"


class StatementStatus(str, Enum):
    DRAFT = "draft"
    APPROVED = "approved"


# --- Core tables ----------------------------------------------------------

class Company(Base):
    __tablename__ = "companies"

    id: Mapped[uuid.UUID] = _uuid_pk()
    name: Mapped[str] = mapped_column(String(200), index=True)
    sector: Mapped[str] = mapped_column(String(120), default="")
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    fiscal_year_end: Mapped[str] = mapped_column(String(16), default="March")
    created_at: Mapped[datetime] = _now()

    filings: Mapped[list["Filing"]] = relationship(back_populates="company",
                                                   cascade="all, delete-orphan")


class Filing(Base):
    __tablename__ = "filings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    doc_type: Mapped[FilingDocType] = mapped_column(
        _str_enum(FilingDocType), default=FilingDocType.ANNUAL_REPORT)
    file_path: Mapped[str] = mapped_column(Text)
    checksum: Mapped[str] = mapped_column(String(64), default="")
    status: Mapped[str] = mapped_column(String(32), default="pending")
    num_pages: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _now()

    company: Mapped[Company] = relationship(back_populates="filings")
    statements: Mapped[list["FinancialStatement"]] = relationship(
        back_populates="filing", cascade="all, delete-orphan")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="filing",
                                                  cascade="all, delete-orphan")


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    filing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("filings.id", ondelete="CASCADE"), index=True)
    state: Mapped[JobState] = mapped_column(_str_enum(JobState), default=JobState.PENDING)
    stage_detail: Mapped[str] = mapped_column(Text, default="")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = _now()


class FinancialStatement(Base):
    __tablename__ = "financial_statements"
    __table_args__ = (UniqueConstraint("filing_id", "period", "statement_type",
                                       name="uq_statement_filing_period_type"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    filing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("filings.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    period: Mapped[str] = mapped_column(String(16), index=True)  # FY2025
    statement_type: Mapped[StatementType] = mapped_column(
        _str_enum(StatementType), index=True)
    status: Mapped[StatementStatus] = mapped_column(
        _str_enum(StatementStatus), default=StatementStatus.DRAFT)
    created_at: Mapped[datetime] = _now()

    filing: Mapped[Filing] = relationship(back_populates="statements")
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="statement", cascade="all, delete-orphan")


class LineItem(Base):
    __tablename__ = "line_items"
    __table_args__ = (UniqueConstraint("statement_id", "canonical_key",
                                       name="uq_lineitem_statement_key"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    statement_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("financial_statements.id", ondelete="CASCADE"), index=True)
    canonical_key: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    unit: Mapped[str] = mapped_column(String(16), default="INR_cr")
    page_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    raw_label: Mapped[str] = mapped_column(Text, default="")
    confidence: Mapped[float] = mapped_column(Float, default=1.0)
    method: Mapped[str] = mapped_column(String(32), default="seed")  # seed|alias|fuzzy|llm_hint|derived
    source: Mapped[str] = mapped_column(String(32), default="fixture")
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = _now()

    statement: Mapped[FinancialStatement] = relationship(back_populates="line_items")


class AssumptionSet(Base):
    __tablename__ = "assumption_sets"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="base")
    payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = _now()


class DcfRun(Base):
    __tablename__ = "dcf_runs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    assumption_set_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("assumption_sets.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    result: Mapped[dict] = mapped_column(JSONB, default=dict)
    checks: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = _now()


class RiskAssessment(Base):
    __tablename__ = "risk_assessments"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    flags: Mapped[list] = mapped_column(JSONB, default=list)
    composite_score: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _now()


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = _uuid_pk()
    filing_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("filings.id", ondelete="CASCADE"), index=True)
    page_no: Mapped[int] = mapped_column(Integer, default=0)
    section: Mapped[str] = mapped_column(String(200), default="")
    chunk_idx: Mapped[int] = mapped_column(Integer, default=0)
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(get_settings().embedding_dim), nullable=True)
    tsv: Mapped[str | None] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', text)", persisted=True), nullable=True)

    filing: Mapped[Filing] = relationship(back_populates="chunks")


class QaLog(Base):
    __tablename__ = "qa_logs"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text, default="")
    citations: Mapped[list] = mapped_column(JSONB, default=list)
    grounded: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    tokens: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _now()


class LlmCall(Base):
    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = _uuid_pk()
    provider: Mapped[str] = mapped_column(String(32))
    model: Mapped[str] = mapped_column(String(64))
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_inr: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    request_id: Mapped[str] = mapped_column(String(32), default="")
    created_at: Mapped[datetime] = _now()


class Peer(Base):
    __tablename__ = "peers"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True)  # owning target
    name: Mapped[str] = mapped_column(String(200), index=True)
    sector: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[datetime] = _now()

    metrics: Mapped[list["PeerMetric"]] = relationship(back_populates="peer",
                                                       cascade="all, delete-orphan")


class PeerMetric(Base):
    __tablename__ = "peer_metrics"

    id: Mapped[uuid.UUID] = _uuid_pk()
    peer_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("peers.id", ondelete="CASCADE"), index=True)
    metric_key: Mapped[str] = mapped_column(String(64), index=True)
    value: Mapped[float] = mapped_column(Float)
    period: Mapped[str] = mapped_column(String(16), default="FY2025")
    source: Mapped[str] = mapped_column(String(120), default="manual")

    peer: Mapped[Peer] = relationship(back_populates="metrics")


class ExportArtifact(Base):
    __tablename__ = "export_artifacts"

    id: Mapped[uuid.UUID] = _uuid_pk()
    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16))  # xlsx | memo_pdf | pptx
    file_path: Mapped[str] = mapped_column(Text)
    assumptions_version: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = _now()
