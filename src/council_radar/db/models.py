"""ORM models. Money columns are GBP (not thousands); loaders convert units."""

from __future__ import annotations

from datetime import date

from sqlalchemy import CheckConstraint, Date, Engine, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from finance_ai_core.db import Base

TIERS = ("district", "county", "unitary", "metropolitan", "london_borough", "other")


class Council(Base):
    __tablename__ = "dim_council"
    ons_code: Mapped[str] = mapped_column(String(9), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    tier: Mapped[str] = mapped_column(String(20))
    region: Mapped[str | None] = mapped_column(String(60))
    valid_from: Mapped[date | None] = mapped_column(Date)
    valid_to: Mapped[date | None] = mapped_column(Date)
    __table_args__ = (CheckConstraint(f"tier IN {TIERS!r}", name="ck_council_tier"),)


class CodeSuccession(Base):
    __tablename__ = "map_council_code"
    old_code: Mapped[str] = mapped_column(String(9), primary_key=True)
    new_code: Mapped[str] = mapped_column(String(9), primary_key=True)
    effective: Mapped[date] = mapped_column(Date)
    weight: Mapped[float] = mapped_column(Float, default=1.0)


class FinanceYear(Base):
    """One row per council per financial year (year = ending year, 2024 means 2023-24)."""

    __tablename__ = "fact_finance_year"
    ons_code: Mapped[str] = mapped_column(ForeignKey("dim_council.ons_code"), primary_key=True)
    year: Mapped[int] = mapped_column(primary_key=True)
    net_revenue_expenditure: Mapped[float | None] = mapped_column(Float)
    reserves_unallocated: Mapped[float | None] = mapped_column(Float)
    reserves_earmarked: Mapped[float | None] = mapped_column(Float)
    dsg_deficit: Mapped[float | None] = mapped_column(Float)
    external_borrowing: Mapped[float | None] = mapped_column(Float)
    commercial_property: Mapped[float | None] = mapped_column(Float)
    interest_cost: Mapped[float | None] = mapped_column(Float)
    core_spending_power: Mapped[float | None] = mapped_column(Float)
    social_care_spend: Mapped[float | None] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(200))


class Event(Base):
    """Distress events: Section 114 notices and Exceptional Financial Support."""

    __tablename__ = "fact_event"
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ons_code: Mapped[str] = mapped_column(ForeignKey("dim_council.ons_code"))
    event_type: Mapped[str] = mapped_column(String(10))
    event_date: Mapped[date] = mapped_column(Date)
    financial_year: Mapped[int]  # ending year; for s114 derived from the notice date
    amount_gbp: Mapped[float | None] = mapped_column(Float)
    verification: Mapped[str] = mapped_column(String(20))
    source_url: Mapped[str | None] = mapped_column(String(400))
    __table_args__ = (
        UniqueConstraint("ons_code", "event_type", "event_date", "financial_year", name="uq_event"),
        CheckConstraint("event_type IN ('s114', 'efs')", name="ck_event_type"),
        CheckConstraint(
            "verification IN ('primary', 'secondary', 'unverified')", name="ck_event_verif"
        ),
    )


class RiskScore(Base):
    __tablename__ = "fact_risk_score"
    ons_code: Mapped[str] = mapped_column(ForeignKey("dim_council.ons_code"), primary_key=True)
    year: Mapped[int] = mapped_column(primary_key=True)
    model: Mapped[str] = mapped_column(String(40), primary_key=True)
    score: Mapped[float | None] = mapped_column(Float)
    coverage: Mapped[float] = mapped_column(Float)
    top_drivers: Mapped[str] = mapped_column(String(200))


def create_schema(engine: Engine) -> None:
    """Create all Council Radar tables (idempotent)."""
    Base.metadata.create_all(engine)
