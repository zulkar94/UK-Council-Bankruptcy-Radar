"""Extraction schema for Section 25 robustness statements (Local Government Act 2003).

The chief finance officer must report on the robustness of budget estimates and
the adequacy of reserves. These fields are what the AI layer pulls out.
"""

from __future__ import annotations

from pydantic import BaseModel

from finance_ai_core.extraction.schema import ExtractedField


class S25Extract(BaseModel):
    budget_gap_gbp_m: ExtractedField[float]
    reserves_judged_adequate: ExtractedField[bool]
    efs_requested_or_planned: ExtractedField[bool]
    s114_risk_mentioned: ExtractedField[bool]
    savings_target_gbp_m: ExtractedField[float]
