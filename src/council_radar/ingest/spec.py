"""Column map specs, stored as TOML so a new file layout needs no code change."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path
from typing import Any, Literal

YearFormat = Literal["int", "fy_label", "yyyymm"]
TEXT_COLUMNS = frozenset({"ons_code", "name"})


@dataclass(frozen=True)
class SourceSpec:
    name: str
    # canonical -> raw header, or a list of raw headers to add together
    columns: dict[str, str | tuple[str, ...]]
    money_columns: tuple[str, ...]
    units_multiplier: float = 1.0
    sheet: str | int | None = None
    header_row: int = 0
    year_column: str | None = None
    year_format: YearFormat = "int"
    fixed_year: int | None = None
    aggregate_code_regex: str | None = None  # codes of total rows to skip, not reject
    description: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def raw_headers(self) -> list[str]:
        out: list[str] = []
        for v in self.columns.values():
            out += [v] if isinstance(v, str) else list(v)
        return out

    def __post_init__(self) -> None:
        if "ons_code" not in self.columns:
            raise ValueError(f"spec {self.name!r} must map ons_code")
        if (self.year_column is None) == (self.fixed_year is None):
            raise ValueError(f"spec {self.name!r} needs exactly one of year.column or year.fixed")
        if any(not isinstance(self.columns[c], str) for c in TEXT_COLUMNS & set(self.columns)):
            raise ValueError(f"spec {self.name!r}: text columns cannot be summed")
        bad = set(self.money_columns) - set(self.columns)
        if bad:
            raise ValueError(f"spec {self.name!r} money columns not mapped: {sorted(bad)}")


def parse_spec(data: dict[str, Any]) -> SourceSpec:
    src = data.get("source", {})
    year = data.get("year", {})
    return SourceSpec(
        name=src["name"],
        description=src.get("description", ""),
        sheet=src.get("sheet"),
        header_row=int(src.get("header_row", 0)),
        units_multiplier=float(src.get("units_multiplier", 1.0)),
        columns={k: v if isinstance(v, str) else tuple(v) for k, v in data["columns"].items()},
        aggregate_code_regex=src.get("aggregate_code_regex"),
        money_columns=tuple(src.get("money_columns", [])),
        year_column=year.get("column"),
        year_format=year.get("format", "int"),
        fixed_year=year.get("fixed"),
    )


def load_spec(path: Path) -> SourceSpec:
    with path.open("rb") as fh:
        return parse_spec(tomllib.load(fh))


def builtin_spec(name: str) -> SourceSpec:
    ref = resources.files("council_radar.ingest").joinpath("column_maps", f"{name}.toml")
    with ref.open("rb") as fh:
        return parse_spec(tomllib.load(fh))
