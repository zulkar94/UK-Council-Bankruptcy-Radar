from __future__ import annotations

import pandas as pd
import pytest

from council_radar.domain.codes import tier_from_code
from council_radar.ingest.loader import load_frame
from council_radar.ingest.spec import builtin_spec

from ..conftest import SAMPLE


@pytest.fixture(scope="module")
def sample() -> tuple[pd.DataFrame, pd.DataFrame]:
    panel, _ = load_frame(SAMPLE / "finance_year.csv", builtin_spec("sample_finance_year"))
    panel["tier"] = panel["ons_code"].map(tier_from_code)
    councils = pd.read_csv(SAMPLE / "councils.csv", dtype=str)
    code_by_name = dict(zip(councils["name"], councils["ons_code"], strict=True))
    ev = pd.read_csv(SAMPLE / "events.csv", dtype=str)
    events = pd.DataFrame(
        {
            "ons_code": ev["council_name"].map(code_by_name),
            "event_date": pd.to_datetime(ev["event_date"]).dt.date,
            "verification": ev["verification"],
        }
    )
    return panel, events
