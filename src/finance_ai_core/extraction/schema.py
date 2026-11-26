"""Schema primitives for AI-extracted fields. Every value must carry a citation."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

MAX_QUOTE_CHARS = 400


class Citation(BaseModel):
    """Where in the source document a value came from."""

    model_config = ConfigDict(frozen=True)

    doc_id: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    quote: str = Field(min_length=1, max_length=MAX_QUOTE_CHARS)


class ExtractedField[T](BaseModel):
    """A single extracted value with model confidence and a verifiable citation.

    ``value`` may be None when the document does not state the item. In that
    case ``citation`` may also be None.
    """

    model_config = ConfigDict(frozen=True)

    value: T | None
    confidence: float = Field(ge=0.0, le=1.0)
    citation: Citation | None = None
