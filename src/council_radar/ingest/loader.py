"""Read CSV/XLSX/ODS files into canonical frames with a validation report.

Government statistics use markers like "..", "x", "[c]" or "-" for missing or
suppressed values. These become NaN and are counted, never silently zeroed.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from council_radar.ingest.spec import SourceSpec

ONS_CODE = re.compile(r"^[EWSN]\d{8}$")
MISSING_MARKERS = {"", "-", "..", "...", "x", "[x]", "[c]", "[z]", "n/a", "na", ":", "nan"}
YEAR_DIGITS = 4
_FY = re.compile(r"^\s*(\d{4})\s*[-/]\s*(\d{2}|\d{4})\s*$")


class SpecMismatchError(ValueError):
    """Raised when a file does not contain the headers a spec expects."""


@dataclass
class ValidationReport:
    source: str
    rows_in: int = 0
    rows_out: int = 0
    bad_codes: list[str] = field(default_factory=list)
    coerced_to_null: dict[str, int] = field(default_factory=dict)
    duplicate_keys: int = 0
    bad_years: int = 0

    @property
    def ok(self) -> bool:
        return self.rows_out > 0 and not self.bad_codes and self.bad_years == 0

    def summary(self) -> str:
        nulls = sum(self.coerced_to_null.values())
        return (
            f"[{self.source}] in={self.rows_in} out={self.rows_out} "
            f"bad_codes={len(self.bad_codes)} bad_years={self.bad_years} "
            f"dupes={self.duplicate_keys} nulls_from_markers={nulls}"
        )


def read_raw(path: Path, spec: SourceSpec) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path, header=spec.header_row, dtype=str, keep_default_na=False)
    if suffix in {".xlsx", ".xlsm"}:
        return pd.read_excel(
            path, sheet_name=spec.sheet or 0, header=spec.header_row, dtype=str, engine="openpyxl"
        )
    if suffix == ".ods":
        return pd.read_excel(
            path, sheet_name=spec.sheet or 0, header=spec.header_row, dtype=str, engine="odf"
        )
    raise ValueError(f"unsupported file type: {suffix}")


def parse_fy(value: str) -> int | None:
    """'2023-24' or '2023/2024' -> 2024 (ending year). Plain '2024' -> 2024."""
    v = str(value).strip()
    if v.isdigit() and len(v) == YEAR_DIGITS:
        return int(v)
    m = _FY.match(v)
    if not m:
        return None
    start, end = int(m.group(1)), m.group(2)
    end_full = int(end) if len(end) == YEAR_DIGITS else (start // 100) * 100 + int(end)
    if end_full < start:  # e.g. 1999-00
        end_full += 100
    return end_full if end_full == start + 1 else None


def _to_number(s: pd.Series) -> tuple[pd.Series, int]:
    cleaned = s.astype(str).str.strip().str.replace(r"[£,\s]", "", regex=True)
    is_marker = cleaned.str.casefold().isin(MISSING_MARKERS)
    neg_paren = cleaned.str.match(r"^\(.*\)$")
    cleaned = cleaned.where(~neg_paren, "-" + cleaned.str.strip("()"))
    num = pd.to_numeric(cleaned.where(~is_marker), errors="coerce")
    failed = int((num.isna() & ~is_marker).sum())
    return num, int(is_marker.sum()) + failed


def load_frame(path: Path, spec: SourceSpec) -> tuple[pd.DataFrame, ValidationReport]:
    raw = read_raw(path, spec)
    raw.columns = [str(c).strip() for c in raw.columns]
    report = ValidationReport(source=spec.name, rows_in=len(raw))

    needed = dict(spec.columns)
    if spec.year_column:
        needed["__year__"] = spec.year_column
    missing = [h for h in needed.values() if h not in raw.columns]
    if missing:
        hints = {h: difflib.get_close_matches(h, list(raw.columns), n=2) for h in missing}
        raise SpecMismatchError(f"{spec.name}: headers not found {hints}")

    df = pd.DataFrame({canon: raw[hdr] for canon, hdr in spec.columns.items()})
    df["ons_code"] = df["ons_code"].astype(str).str.strip().str.upper()
    df = df[df["ons_code"].ne("") & df["ons_code"].ne("NAN")]

    valid = df["ons_code"].str.match(ONS_CODE)
    report.bad_codes = sorted(df.loc[~valid, "ons_code"].unique().tolist())
    df = df[valid].copy()

    if spec.year_column:
        years = raw.loc[df.index, spec.year_column].map(
            parse_fy if spec.year_format == "fy_label" else _int_or_none
        )
        report.bad_years = int(years.isna().sum())
        df["year"] = years
        df = df[df["year"].notna()]
        df["year"] = df["year"].astype(int)
    else:
        df["year"] = spec.fixed_year

    for col in df.columns:
        if col in {"ons_code", "year"} or col not in spec.columns:
            continue
        num, nulls = _to_number(df[col])
        if nulls:
            report.coerced_to_null[col] = nulls
        df[col] = num * spec.units_multiplier if col in spec.money_columns else num

    before = len(df)
    df = df.drop_duplicates(subset=["ons_code", "year"], keep="last")
    report.duplicate_keys = before - len(df)
    report.rows_out = len(df)
    return df.reset_index(drop=True), report


def _int_or_none(v: object) -> int | None:
    s = str(v).strip()
    return int(s) if s.isdigit() else None


def inspect_headers(path: Path, header_row: int = 0, sheet: str | int | None = None) -> list[str]:
    """List headers of a downloaded file so a column map can be written quickly."""
    probe = SourceSpec(
        name="probe",
        columns={"ons_code": "_"},
        money_columns=(),
        sheet=sheet,
        header_row=header_row,
        fixed_year=0,
    )
    return [str(c).strip() for c in read_raw(path, probe).columns]
