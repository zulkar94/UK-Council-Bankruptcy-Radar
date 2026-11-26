"""Command line entry point: `council-radar <command>`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from council_radar.db import repo
from council_radar.db.models import create_schema
from council_radar.domain.rules import rule_score
from council_radar.domain.signals import compute_signals
from council_radar.ingest.loader import inspect_headers, load_frame
from council_radar.ingest.spec import builtin_spec, load_spec
from finance_ai_core.config import Settings
from finance_ai_core.db import make_engine, session_scope

RULE_MODEL = "rules_v1"


@contextmanager
def _engine(args: argparse.Namespace) -> Iterator[Engine]:
    engine = make_engine(args.db or Settings.from_env().database_url)
    try:
        yield engine
    finally:
        engine.dispose()


@contextmanager
def _session(args: argparse.Namespace) -> Iterator[Session]:
    with _engine(args) as engine, session_scope(engine) as session:
        yield session


def _csv(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def cmd_init_db(args: argparse.Namespace) -> int:
    with _engine(args) as engine:
        create_schema(engine)
    print("schema ready")
    return 0


def cmd_load_councils(args: argparse.Namespace) -> int:
    with _session(args) as s:
        n = repo.load_councils(s, _csv(args.file))
    print(f"councils upserted: {n}")
    return 0


def cmd_load_codemap(args: argparse.Namespace) -> int:
    with _session(args) as s:
        n = repo.load_codemap(s, _csv(args.file))
    print(f"code successions upserted: {n}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    spec_path = Path(args.spec)
    spec = load_spec(spec_path) if spec_path.suffix == ".toml" else builtin_spec(args.spec)
    frame, report = load_frame(Path(args.file), spec)
    print(report.summary())
    if report.bad_codes:
        print(f"  rejected codes: {report.bad_codes[:10]}")
    if not report.ok and not args.force:
        print("validation failed; fix the file or re-run with --force", file=sys.stderr)
        return 2
    with _session(args) as s:
        res = repo.load_finance(s, frame, source=spec.name)
    print(f"rows written: {res.written}")
    if res.unknown_codes:
        print(f"  codes not in dim_council (skipped): {res.unknown_codes[:10]}")
    return 0


def cmd_load_events(args: argparse.Namespace) -> int:
    with _session(args) as s:
        m = repo.load_events(s, _csv(args.file))
    print(f"matched: {len(m.matched)} ambiguous: {len(m.ambiguous)} unmatched: {len(m.unmatched)}")
    for name in m.unmatched:
        print(f"  unmatched: {name}")
    for name, codes in m.ambiguous.items():
        print(f"  ambiguous: {name} -> {codes}")
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    for h in inspect_headers(Path(args.file), header_row=args.header_row, sheet=args.sheet):
        print(h)
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    with _session(args) as s:
        panel = repo.finance_panel(s)
        if panel.empty:
            print("no finance data loaded", file=sys.stderr)
            return 1
        scores = rule_score(compute_signals(panel))
        n = repo.save_scores(s, scores, RULE_MODEL)
    print(f"scores written: {n} (model={RULE_MODEL})")
    if args.out:
        scores.to_csv(args.out, index=False)
        print(f"exported: {args.out}")
    latest = scores[scores["year"] == scores["year"].max()]
    top = latest.sort_values("score", ascending=False).head(args.top)
    print(top.to_string(index=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="council-radar", description=__doc__)
    p.add_argument("--db", help="SQLAlchemy URL (default: FAI_DATABASE_URL or local SQLite)")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-db", help="create tables").set_defaults(fn=cmd_init_db)

    for name, fn, helptext in (
        ("load-councils", cmd_load_councils, "load dim_council CSV"),
        ("load-codemap", cmd_load_codemap, "load ONS code succession CSV"),
        ("load-events", cmd_load_events, "load s114/EFS reference CSV"),
    ):
        sp = sub.add_parser(name, help=helptext)
        sp.add_argument("file")
        sp.set_defaults(fn=fn)

    sp = sub.add_parser("ingest", help="ingest a finance file using a column map")
    sp.add_argument("spec", help="built-in spec name or path to a .toml column map")
    sp.add_argument("file")
    sp.add_argument("--force", action="store_true", help="load even if validation flags issues")
    sp.set_defaults(fn=cmd_ingest)

    sp = sub.add_parser("inspect", help="print headers of a downloaded file")
    sp.add_argument("file")
    sp.add_argument("--header-row", type=int, default=0)
    sp.add_argument("--sheet", default=None)
    sp.set_defaults(fn=cmd_inspect)

    sp = sub.add_parser("score", help="compute signals and baseline rule score")
    sp.add_argument("--out", help="write scores CSV (for Power BI)")
    sp.add_argument("--top", type=int, default=10)
    sp.set_defaults(fn=cmd_score)
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    code: int = args.fn(args)
    return code


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
