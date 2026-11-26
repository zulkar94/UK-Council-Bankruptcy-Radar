from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from council_radar.ingest.loader import (
    SpecMismatchError,
    extract_councils,
    inspect_headers,
    load_frame,
    parse_fy,
    parse_yyyymm,
)
from council_radar.ingest.spec import SourceSpec, builtin_spec, load_spec, parse_spec

from ..conftest import FINANCE_ROWS, SAMPLE

SPEC = SourceSpec(
    name="t",
    columns={"ons_code": "Code", "net_revenue_expenditure": "NRE", "dsg_deficit": "DSG"},
    money_columns=("net_revenue_expenditure", "dsg_deficit"),
    units_multiplier=1000,
    year_column="Year",
    year_format="fy_label",
)


@pytest.mark.parametrize(
    ("raw", "year"),
    [
        ("2023-24", 2024),
        ("2023/2024", 2024),
        ("1999-00", 2000),
        ("2024", 2024),
        ("2023-25", None),
        ("FY23", None),
    ],
)
def test_parse_fy(raw: str, year: int | None) -> None:
    assert parse_fy(raw) == year


def write(tmp: Path, rows: list[dict[str, str]], name: str = "f.csv") -> Path:
    p = tmp / name
    pd.DataFrame(rows).to_csv(p, index=False)
    return p


def test_load_frame_units_markers_codes_dupes(tmp_path: Path) -> None:
    rows = [
        {"Code": "E06000018", "Year": "2022-23", "NRE": "1,234", "DSG": ".."},
        {"Code": "e06000018 ", "Year": "2022-23", "NRE": "2,000", "DSG": "(5)"},  # dup, later wins
        {"Code": "BADCODE", "Year": "2022-23", "NRE": "1", "DSG": "1"},
        {"Code": "E09000008", "Year": "garbage", "NRE": "£3,000", "DSG": "abc"},
        {"Code": "E08000025", "Year": "2023-24", "NRE": "[x]", "DSG": "7"},
    ]
    df, rep = load_frame(write(tmp_path, rows), SPEC)
    assert rep.rows_in == 5
    assert rep.bad_codes == ["BADCODE"]
    assert rep.bad_years == 1
    assert rep.duplicate_keys == 1
    assert not rep.ok
    by = df.set_index("ons_code")
    assert by.loc["E06000018", "net_revenue_expenditure"] == 2_000_000
    assert by.loc["E06000018", "dsg_deficit"] == -5000
    assert pd.isna(by.loc["E08000025", "net_revenue_expenditure"])
    assert rep.coerced_to_null["net_revenue_expenditure"] == 1
    assert "bad_codes=1" in rep.summary()


def test_header_mismatch_suggests(tmp_path: Path) -> None:
    p = write(tmp_path, [{"Code": "E06000018", "Year": "2023-24", "Net rev": "1", "DSG": "1"}])
    with pytest.raises(SpecMismatchError, match="NRE"):
        load_frame(p, SPEC)


def test_fixed_year_and_int_format(tmp_path: Path) -> None:
    spec = SourceSpec(name="f", columns={"ons_code": "Code"}, money_columns=(), fixed_year=2024)
    df, rep = load_frame(write(tmp_path, [{"Code": "E06000018"}]), spec)
    assert df.year.tolist() == [2024]
    assert rep.ok
    spec2 = SourceSpec(name="i", columns={"ons_code": "Code"}, money_columns=(), year_column="Y")
    df2, rep2 = load_frame(
        write(tmp_path, [{"Code": "E06000018", "Y": "2021"}, {"Code": "E06000019", "Y": "x"}]),
        spec2,
    )
    assert df2.year.tolist() == [2021]
    assert rep2.bad_years == 1


def test_xlsx_and_ods(tmp_path: Path) -> None:
    frame = pd.DataFrame([{"Code": "E06000018", "Year": "2023-24", "NRE": 5, "DSG": None}])
    for suffix, engine in ((".xlsx", "openpyxl"), (".ods", "odf")):
        p = tmp_path / f"f{suffix}"
        frame.to_excel(p, index=False, engine=engine)
        df, rep = load_frame(p, SPEC)
        assert df.loc[0, "net_revenue_expenditure"] == 5000
        assert rep.coerced_to_null.get("dsg_deficit") == 1
        assert inspect_headers(p) == ["Code", "Year", "NRE", "DSG"]


def test_unsupported_suffix(tmp_path: Path) -> None:
    p = tmp_path / "f.json"
    p.write_text("{}")
    with pytest.raises(ValueError, match="unsupported"):
        load_frame(p, SPEC)


@pytest.mark.parametrize(
    ("kwargs", "msg"),
    [
        ({"columns": {"x": "X"}, "money_columns": (), "fixed_year": 1}, "ons_code"),
        ({"columns": {"ons_code": "C"}, "money_columns": ()}, "exactly one"),
        ({"columns": {"ons_code": "C"}, "money_columns": ("nre",), "fixed_year": 1}, "money"),
    ],
)
def test_spec_validation(kwargs: dict[str, object], msg: str) -> None:
    with pytest.raises(ValueError, match=msg):
        SourceSpec(name="bad", **kwargs)  # type: ignore[arg-type]


def test_builtin_and_file_specs(tmp_path: Path) -> None:
    spec = builtin_spec("sample_finance_year")
    assert spec.units_multiplier == 1000
    df, rep = load_frame(SAMPLE / "finance_year.csv", spec)
    assert rep.ok
    assert len(df) == FINANCE_ROWS
    ro = builtin_spec("ro_multi_year")
    assert ro.columns["social_care_spend"] == ("RS_asc_net_exp", "RS_csc_net_exp")
    p = tmp_path / "s.toml"
    p.write_text('[source]\nname="x"\n[year]\nfixed=2020\n[columns]\nons_code="C"\n')
    assert load_spec(p).fixed_year == 2020
    assert parse_spec({"source": {"name": "y"}, "year": {"fixed": 1}, "columns": {"ons_code": "C"}})


RO_FIXTURE = SAMPLE.parents[1] / "tests" / "fixtures" / "ro_layout_sample.csv"


def test_real_outturn_layout() -> None:
    df, rep = load_frame(RO_FIXTURE, builtin_spec("ro_multi_year"))
    assert rep.aggregate_rows == 2  # class total and England total skipped, not rejected
    assert rep.bad_codes == []
    assert rep.ok
    by = df.set_index(["ons_code", "year"])
    assert by.loc[("E06000001", 2018), "social_care_spend"] == 70_000_000
    assert by.loc[("E06000001", 2018), "net_revenue_expenditure"] == 95_000_000
    # "Not set" in one part of a sum leaves the other part; both missing gives NaN.
    assert by.loc[("E06000001", 2019), "social_care_spend"] == 31_000_000
    assert pd.isna(by.loc[("E06000999", 2018), "social_care_spend"])
    assert rep.coerced_to_null["RS_asc_net_exp"] == 2
    assert "totals_skipped=2" in rep.summary()


def test_extract_councils_uses_latest_name() -> None:
    df, _ = load_frame(RO_FIXTURE, builtin_spec("ro_multi_year"))
    councils = extract_councils(df).set_index("ons_code")["name"]
    assert councils["E06000001"] == "Hartlepool"
    assert list(councils.index) == ["E06000001", "E06000999", "E07000217"]
    with pytest.raises(ValueError, match="name column"):
        extract_councils(df.drop(columns="name"))


def test_parse_yyyymm() -> None:
    assert parse_yyyymm("202503") == 2025
    assert parse_yyyymm("2025") is None
    assert parse_yyyymm("20250x") is None


def test_text_columns_cannot_be_summed() -> None:
    with pytest.raises(ValueError, match="text columns"):
        SourceSpec(name="x", columns={"ons_code": ("A", "B")}, money_columns=(), fixed_year=2020)
