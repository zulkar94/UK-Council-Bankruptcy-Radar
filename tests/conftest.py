from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Engine

from council_radar.db.models import create_schema
from finance_ai_core.db import make_engine

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"
REFERENCE = ROOT / "data" / "reference"


@pytest.fixture
def engine(tmp_path: Path) -> Iterator[Engine]:
    eng = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    create_schema(eng)
    yield eng
    eng.dispose()
