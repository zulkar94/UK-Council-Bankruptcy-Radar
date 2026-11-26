from __future__ import annotations

import json
from typing import Any

import pytest

from council_radar.domain.s25 import S25Extract
from finance_ai_core.extraction import ExtractionError, extract, score_extractions
from finance_ai_core.extraction.extractor import quote_in_source

DOC = """Section 25 statement 2025/26.
The Council faces a budget gap of £42.5m in 2025/26.
In my view the level of reserves is not adequate.
The Council has submitted a request for Exceptional Financial Support.
"""


class FakeClient:
    def __init__(self, payload: dict[str, Any] | str) -> None:
        self.payload = payload
        self.seen: dict[str, Any] = {}

    def complete_json(self, system: str, user: str, json_schema: dict[str, Any]) -> str:
        self.seen = {"system": system, "user": user, "schema": json_schema}
        return self.payload if isinstance(self.payload, str) else json.dumps(self.payload)


def field(value: Any, quote: str | None, conf: float = 0.9) -> dict[str, Any]:
    cit = {"doc_id": "d1", "page": 1, "quote": quote} if quote else None
    return {"value": value, "confidence": conf, "citation": cit}


GOOD = {
    "budget_gap_gbp_m": field(42.5, "budget gap of £42.5m in 2025/26"),
    "reserves_judged_adequate": field(False, "the level of reserves is not adequate"),
    "efs_requested_or_planned": field(
        True, "submitted a request for   Exceptional Financial Support"
    ),
    "s114_risk_mentioned": field(None, None, 0.0),
    # Hallucinated: the quote does not exist in the document.
    "savings_target_gbp_m": field(18.0, "savings of £18m are required"),
}


def test_extract_verifies_citations() -> None:
    client = FakeClient(GOOD)
    result, rejected = extract(client, S25Extract, "d1", DOC)
    assert rejected == ["savings_target_gbp_m"]
    assert result.savings_target_gbp_m.value is None
    assert result.savings_target_gbp_m.confidence == 0.0
    assert result.budget_gap_gbp_m.value == 42.5
    assert result.efs_requested_or_planned.value is True  # whitespace-insensitive match
    assert "data, not instructions" in client.seen["system"]
    assert "<document>" in client.seen["user"]


def test_missing_citation_is_rejected() -> None:
    payload = dict(GOOD)
    payload["budget_gap_gbp_m"] = field(42.5, None)
    result, rejected = extract(FakeClient(payload), S25Extract, "d1", DOC)
    assert "budget_gap_gbp_m" in rejected
    assert result.budget_gap_gbp_m.value is None


@pytest.mark.parametrize("bad", ["not json", json.dumps({"budget_gap_gbp_m": 5})])
def test_invalid_output_raises(bad: str) -> None:
    with pytest.raises(ExtractionError):
        extract(FakeClient(bad), S25Extract, "d1", DOC)


def test_quote_in_source_normalises() -> None:
    assert quote_in_source("BUDGET  GAP\nof", DOC)
    assert not quote_in_source("surplus", DOC)


def test_score_extractions() -> None:
    result, _ = extract(FakeClient(GOOD), S25Extract, "d1", DOC)
    gold = {
        "budget_gap_gbp_m": 42.0,  # 42.5 vs 42.0 is 1.19%: outside default 1% tolerance
        "reserves_judged_adequate": False,
        "efs_requested_or_planned": True,
        "s114_risk_mentioned": None,
        "savings_target_gbp_m": 18.0,
    }
    scores = score_extractions([result], [gold])
    assert scores["budget_gap_gbp_m"].false_pos == 1
    assert scores["budget_gap_gbp_m"].false_neg == 1
    assert scores["reserves_judged_adequate"].precision == 1.0
    assert scores["s114_risk_mentioned"].true_neg == 1
    assert scores["savings_target_gbp_m"].recall == 0.0
    loose = score_extractions([result], [gold], rel_tol=0.02)
    assert loose["budget_gap_gbp_m"].true_pos == 1


def test_score_value_types_and_lengths() -> None:
    result, _ = extract(FakeClient(GOOD), S25Extract, "d1", DOC)
    gold = {"budget_gap_gbp_m": None, "reserves_judged_adequate": True}
    s = score_extractions([result], [gold])
    assert s["budget_gap_gbp_m"].false_pos == 1
    assert s["reserves_judged_adequate"].true_pos == 0
    assert s["efs_requested_or_planned"].precision == 0.0
    with pytest.raises(ValueError, match="same length"):
        score_extractions([result], [])
