"""Load canonical frames into the database and read them back for scoring."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pandas as pd
from sqlalchemy import Table, select
from sqlalchemy.orm import Session

from council_radar.db.models import TIERS, CodeSuccession, Council, Event, FinanceYear, RiskScore
from council_radar.domain.codes import CodeMap, Succession, tier_from_code
from council_radar.domain.names import MatchResult, match_names
from finance_ai_core.db import upsert

FINANCE_FIELDS = tuple(
    c.name for c in FinanceYear.__table__.columns if c.name not in {"ons_code", "year", "source"}
)


APRIL = 4


def _table(model: type[Any]) -> Table:
    tbl = model.__table__
    if not isinstance(tbl, Table):
        raise TypeError(f"{model.__name__} is not mapped to a Table")
    return tbl


def _records(df: pd.DataFrame) -> list[dict[str, Any]]:
    clean = df.astype(object).where(df.notna(), None)
    return [{str(k): v for k, v in row.items()} for row in clean.to_dict(orient="records")]


def _opt_date(v: Any) -> date | None:
    if v is None or (isinstance(v, float) and pd.isna(v)) or str(v).strip() == "":
        return None
    return date.fromisoformat(str(v).strip())


def financial_year_of(d: date) -> int:
    """UK local government year runs April to March. Returns the ending year."""
    return d.year + 1 if d.month >= APRIL else d.year


def load_councils(session: Session, df: pd.DataFrame) -> int:
    """Tier column is optional; blanks are inferred from the ONS code prefix."""
    df = df.copy()
    if "tier" not in df.columns:
        df["tier"] = ""
    blank = df["tier"].fillna("").astype(str).str.strip() == ""
    df.loc[blank, "tier"] = df.loc[blank, "ons_code"].astype(str).map(tier_from_code)
    bad = sorted(set(df["tier"]) - set(TIERS))
    if bad:
        raise ValueError(f"unknown tiers: {bad}")
    rows = [
        {
            "ons_code": str(r["ons_code"]).strip().upper(),
            "name": str(r["name"]).strip(),
            "tier": r["tier"],
            "region": r.get("region") or None,
            "valid_from": _opt_date(r.get("valid_from")),
            "valid_to": _opt_date(r.get("valid_to")),
        }
        for r in _records(df)
    ]
    return upsert(session, _table(Council), rows, ["ons_code"])


def load_codemap(session: Session, df: pd.DataFrame) -> int:
    succs = [
        Succession(
            old_code=str(r["old_code"]).strip().upper(),
            new_code=str(r["new_code"]).strip().upper(),
            effective=date.fromisoformat(str(r["effective"]).strip()),
            weight=float(r.get("weight") or 1.0),
        )
        for r in _records(df)
    ]
    CodeMap(succs)  # validates weights and structure before anything is written
    rows = [
        {
            "old_code": s.old_code,
            "new_code": s.new_code,
            "effective": s.effective,
            "weight": s.weight,
        }
        for s in succs
    ]
    return upsert(session, _table(CodeSuccession), rows, ["old_code", "new_code"])


def known_codes(session: Session) -> set[str]:
    return set(session.scalars(select(Council.ons_code)))


@dataclass
class FinanceLoadResult:
    written: int
    unknown_codes: list[str] = field(default_factory=list)


def load_finance(session: Session, df: pd.DataFrame, source: str) -> FinanceLoadResult:
    known = known_codes(session)
    unknown = sorted(set(df["ons_code"]) - known)
    keep = df[df["ons_code"].isin(known)]
    cols = ["ons_code", "year", *[c for c in FINANCE_FIELDS if c in keep.columns]]
    out = keep[cols].copy()
    out["source"] = source
    written = upsert(session, _table(FinanceYear), _records(out), ["ons_code", "year"])
    return FinanceLoadResult(written=written, unknown_codes=unknown)


def load_events(session: Session, df: pd.DataFrame) -> MatchResult:
    """Load reference events by council name.

    Several decisions can cover the same (council, type, financial year), e.g. EFS
    support agreed in one round and revised in the next. The row keeps the EARLIEST
    decision date (when the distress first became public, which is what a backtest
    must use to avoid leakage) and the LATEST amount (the best current figure).
    """
    # Build explicitly: Result has .keys(), so dict(result) would treat it as a mapping.
    councils = {
        code: name for code, name in session.execute(select(Council.ons_code, Council.name))
    }
    # An explicit ons_code column pins rows whose names are ambiguous or differ from ONS,
    # e.g. Somerset (county until 2023, then a unitary) or "Medway Towns UA".
    pinned = {
        str(r["council_name"]): str(r["ons_code"]).strip().upper()
        for r in _records(df)
        if str(r.get("ons_code") or "").strip().upper() in councils
    }
    unpinned = df.loc[~df["council_name"].astype(str).isin(pinned), "council_name"]
    match = match_names(unpinned.astype(str), councils)
    match.matched.update(pinned)
    rows: dict[tuple[str, str, int], dict[str, Any]] = {}
    for r in sorted(_records(df), key=lambda x: str(x["event_date"])):
        code = match.matched.get(str(r["council_name"]))
        if code is None:
            continue
        ev_date = date.fromisoformat(str(r["event_date"]).strip())
        fy_raw = r.get("financial_year")
        fy = int(fy_raw) if fy_raw not in (None, "") else financial_year_of(ev_date)
        amt = r.get("amount_gbp_m")
        key = (code, str(r["event_type"]), fy)
        first = rows.get(key)
        rows[key] = {
            "ons_code": code,
            "event_type": r["event_type"],
            "event_date": first["event_date"] if first else ev_date,
            "financial_year": fy,
            "amount_gbp": float(amt) * 1_000_000 if amt not in (None, "") else None,
            "verification": r["verification"],
            "source_url": r.get("source_url") or None,
        }
    # Replace earlier rows for the same key so revisions don't duplicate.
    for code, etype, fy in rows:
        session.query(Event).filter_by(ons_code=code, event_type=etype, financial_year=fy).delete()
    session.add_all(Event(**v) for v in rows.values())
    return match


def council_names(session: Session) -> dict[str, str]:
    return {code: name for code, name in session.execute(select(Council.ons_code, Council.name))}


def finance_panel(session: Session) -> pd.DataFrame:
    stmt = select(FinanceYear, Council.tier).join(Council)
    data = [
        {**{c: getattr(fy, c) for c in ("ons_code", "year", *FINANCE_FIELDS)}, "tier": tier}
        for fy, tier in session.execute(stmt)
    ]
    cols = ["ons_code", "year", "tier", *FINANCE_FIELDS]
    return pd.DataFrame(data, columns=cols)


def save_scores(session: Session, scores: pd.DataFrame, model: str) -> int:
    out = scores[["ons_code", "year", "score", "coverage", "top_drivers"]].copy()
    out["model"] = model
    return upsert(session, _table(RiskScore), _records(out), ["ons_code", "year", "model"])


def events_frame(session: Session, *, include_unverified: bool = False) -> pd.DataFrame:
    stmt = select(Event)
    if not include_unverified:
        stmt = stmt.where(Event.verification != "unverified")
    data = [
        {
            "ons_code": e.ons_code,
            "event_type": e.event_type,
            "event_date": e.event_date,
            "financial_year": e.financial_year,
            "amount_gbp": e.amount_gbp,
            "verification": e.verification,
        }
        for e in session.scalars(stmt)
    ]
    return pd.DataFrame(
        data,
        columns=[
            "ons_code",
            "event_type",
            "event_date",
            "financial_year",
            "amount_gbp",
            "verification",
        ],
    )
