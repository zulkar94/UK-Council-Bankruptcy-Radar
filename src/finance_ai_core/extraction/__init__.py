"""Structured AI extraction with citation verification."""

from finance_ai_core.extraction.extractor import ExtractionError, LLMClient, extract
from finance_ai_core.extraction.schema import Citation, ExtractedField
from finance_ai_core.extraction.scoring import FieldScore, score_extractions

__all__ = [
    "Citation",
    "ExtractedField",
    "ExtractionError",
    "FieldScore",
    "LLMClient",
    "extract",
    "score_extractions",
]
