from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import Column, Engine, Integer, MetaData, String, Table, select

from finance_ai_core.config import DEFAULT_DATABASE_URL, Settings
from finance_ai_core.db import make_engine, session_scope, upsert
from finance_ai_core.extraction.scoring import _match


def test_settings_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FAI_DATABASE_URL", raising=False)
    assert Settings.from_env().database_url == DEFAULT_DATABASE_URL
    monkeypatch.setenv("FAI_DATABASE_URL", "sqlite:///x.db")
    monkeypatch.setenv("FAI_ECHO_SQL", "1")
    s = Settings.from_env()
    assert (s.database_url, s.echo_sql) == ("sqlite:///x.db", True)


META = MetaData()
KV = Table("kv", META, Column("k", String, primary_key=True), Column("v", Integer))
KEYS = Table("keys", META, Column("k", String, primary_key=True))


@pytest.fixture
def eng() -> Iterator[Engine]:
    e = make_engine("sqlite://")
    META.create_all(e)
    yield e
    e.dispose()


def test_upsert_paths(eng: Engine) -> None:
    with session_scope(eng) as s:
        assert upsert(s, KV, [], ["k"]) == 0
        upsert(s, KV, [{"k": "a", "v": 1}], ["k"])
        upsert(s, KV, [{"k": "a", "v": 2}], ["k"])
        upsert(s, KEYS, [{"k": "a"}], ["k"])
        upsert(s, KEYS, [{"k": "a"}], ["k"])  # key-only table: do nothing on conflict
    with session_scope(eng) as s:
        assert s.execute(select(KV.c.v)).scalar_one() == 2
        assert s.execute(select(KEYS.c.k)).scalars().all() == ["a"]


def test_session_scope_rolls_back(eng: Engine) -> None:
    def write_then_fail() -> None:
        with session_scope(eng) as s:
            upsert(s, KV, [{"k": "b", "v": 1}], ["k"])
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        write_then_fail()
    with session_scope(eng) as s:
        assert s.execute(select(KV.c.k)).scalars().all() == []


@pytest.mark.parametrize(
    ("p", "g", "ok"),
    [
        (" Yes ", "yes", True),
        ("a", "b", False),
        (0, 0, True),
        (1, 0, False),
        (True, 1, False),
        ([1], [1], True),
    ],
)
def test_match_types(p: object, g: object, ok: bool) -> None:
    assert _match(p, g, 0.01) is ok
