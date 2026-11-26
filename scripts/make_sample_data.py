"""Generate the synthetic sample panel in data/sample/. Deterministic (seed 42).

All councils, codes and figures are invented. Codes use a 9xx range so they cannot
collide with real ONS codes.

Each council gets a profile, so the backtest has something honest to find:
- healthy: noise only
- distressed: finances drift from an onset year, then a s114 or EFS event 2-3 years later
- recovering: drifts for two years, then recovers with no event (false-positive bait)
- shock: no warning in the numbers, event anyway (a miss no model should catch)

One county splits into two unitaries in 2021, so code succession is exercised too.
"""

from __future__ import annotations

import csv
import random
from dataclasses import dataclass
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "sample"
YEARS = list(range(2016, 2026))  # ending years: 2015-16 .. 2024-25
SPLIT_YEAR = 2022  # first full year for successor unitaries
MARKER_RATE = 0.04  # share of rows given a missing-value marker
RECOVERY_PATH = (0.35, 0.7, 0.35)  # drift by year since onset, then back to 0
rng = random.Random(42)

# prefix: (tier, count, typical net revenue expenditure in GBP thousands)
TIERS = {
    "E06": ("unitary", 12, 260_000),
    "E07": ("district", 14, 18_000),
    "E08": ("metropolitan", 8, 520_000),
    "E09": ("london_borough", 8, 330_000),
}
COUNTY, SUCC_A, SUCC_B = "E10000901", "E06000951", "E06000952"

FIRST = [
    "Ash",
    "Brook",
    "Calder",
    "Dun",
    "Elm",
    "Fern",
    "Glen",
    "Hart",
    "Ivy",
    "Juniper",
    "Kestrel",
    "Lark",
    "Mill",
    "North",
    "Oak",
    "Penn",
    "Quarry",
    "Raven",
    "Stone",
    "Thorn",
    "Upton",
    "Wester",
    "Yarrow",
]
SECOND = ["vale", "mere", "ford", "hollow"]


@dataclass(frozen=True)
class Profile:
    kind: str  # healthy | distressed | recovering | shock
    onset: int | None = None  # first drift year
    event_year: int | None = None  # financial year (ending) of the event
    event_type: str | None = None


# code -> profile. Onsets are staggered so the walk-forward folds all see some events.
PROFILES: dict[str, Profile] = {
    "E06000903": Profile("distressed", 2017, 2020, "s114"),
    "E09000902": Profile("distressed", 2018, 2021, "efs"),
    "E08000904": Profile("distressed", 2019, 2021, "efs"),
    "E07000906": Profile("distressed", 2019, 2022, "s114"),
    "E06000908": Profile("distressed", 2020, 2023, "efs"),
    "E09000905": Profile("distressed", 2020, 2022, "s114"),
    "E07000911": Profile("distressed", 2021, 2024, "efs"),
    "E08000907": Profile("distressed", 2021, 2023, "efs"),
    "E06000911": Profile("distressed", 2022, 2025, "efs"),
    "E07000903": Profile("distressed", 2022, 2024, "s114"),
    "E06000905": Profile("recovering", 2019),
    "E07000909": Profile("recovering", 2020),
    "E08000902": Profile("recovering", 2018),
    "E09000907": Profile("recovering", 2021),
    "E06000910": Profile("shock", None, 2023, "efs"),
    "E07000913": Profile("shock", None, 2022, "s114"),
}


def fy_label(y: int) -> str:
    return f"{y - 1}-{str(y)[2:]}"


def drift(p: Profile, year: int) -> float:
    """0 = healthy, 1 = fully stressed."""
    if p.onset is None or year < p.onset:
        return 0.0
    if p.kind == "recovering":
        step = year - p.onset
        return RECOVERY_PATH[step] if step < len(RECOVERY_PATH) else 0.0
    return min(1.0, 0.35 * (year - p.onset + 1))


def names() -> list[str]:
    out = [f"{a}{b}" for b in SECOND for a in FIRST]
    rng.shuffle(out)
    return out


def money(x: float) -> str:
    return f"{round(x):,}"


def finance_row(code: str, year: int, scale: float, tier: str, d: float) -> dict[str, str]:
    t = YEARS.index(year)
    nre = scale * (1 + 0.04 * t) * rng.uniform(0.95, 1.05)
    reserves_ratio = max(0.02, rng.uniform(0.18, 0.35) - 0.22 * d)
    csp = nre * rng.uniform(0.85, 1.0)
    borrowing = csp * (rng.uniform(0.5, 1.6) + 3.5 * d)
    commercial = csp * (rng.uniform(0.0, 0.25) + 2.0 * d)
    social = 0.0 if tier == "district" else nre * (rng.uniform(0.45, 0.6) + 0.08 * d)
    dsg = 0.0 if tier == "district" else nre * rng.uniform(0.0, 0.03) * (1 + 3 * d)
    row = {
        "ONS code": code,
        "Financial year": fy_label(year),
        "Net revenue expenditure (£000)": money(nre),
        "Unallocated reserves (£000)": money(nre * reserves_ratio * 0.3),
        "Earmarked reserves (£000)": money(nre * reserves_ratio * 0.7),
        "DSG deficit (£000)": money(dsg),
        "External borrowing (£000)": money(borrowing),
        "Commercial property (£000)": money(commercial),
        "Interest payable (£000)": money(borrowing * rng.uniform(0.025, 0.04)),
        "Core spending power (£000)": money(csp),
        "Social care net spend (£000)": money(social),
    }
    if rng.random() < MARKER_RATE:
        row["Commercial property (£000)"] = rng.choice(["..", "[x]", "-"])
    return row


def event_date(event_year: int, event_type: str) -> str:
    # EFS for year Y is decided the February before Y starts; s114 lands mid-year.
    if event_type == "efs":
        return f"{event_year - 1}-02-20"
    return f"{event_year - 1}-11-{rng.randint(3, 27):02d}"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    pool = iter(names())
    councils: list[dict[str, str]] = []
    for prefix, (_tier, n, _) in TIERS.items():
        for i in range(1, n + 1):
            councils.append({"ons_code": f"{prefix}000{900 + i}", "name": f"{next(pool)} Council"})
    councils += [
        {"ons_code": COUNTY, "name": "Synthetic Shire County", "valid_to": "2021-03-31"},
        {"ons_code": SUCC_A, "name": "North Synthetic Shire", "valid_from": "2021-04-01"},
        {"ons_code": SUCC_B, "name": "West Synthetic Shire", "valid_from": "2021-04-01"},
    ]
    fields = ["ons_code", "name", "tier", "region", "valid_from", "valid_to"]
    with (OUT / "councils.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, restval="")
        w.writeheader()
        for c in councils:
            w.writerow({"region": "Synthetic Region", **c})

    with (OUT / "code_succession.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["old_code", "new_code", "effective", "weight"])
        w.writerow([COUNTY, SUCC_A, "2021-04-01", "0.45"])
        w.writerow([COUNTY, SUCC_B, "2021-04-01", "0.55"])

    healthy = Profile("healthy")
    rows = []
    for prefix, (tier, n, scale) in TIERS.items():
        for i in range(1, n + 1):
            code = f"{prefix}000{900 + i}"
            prof = PROFILES.get(code, healthy)
            rows += [finance_row(code, y, scale, tier, drift(prof, y)) for y in YEARS]
    for y in YEARS:
        if y < SPLIT_YEAR:
            rows.append(finance_row(COUNTY, y, 700_000, "county", 0.0))
        else:
            rows.append(finance_row(SUCC_A, y, 315_000, "unitary", 0.0))
            rows.append(finance_row(SUCC_B, y, 385_000, "unitary", 0.0))
    with (OUT / "finance_year.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    by_code = {c["ons_code"]: c["name"] for c in councils}
    events = [
        (c, p.event_year, p.event_type)
        for c, p in PROFILES.items()
        if p.event_year is not None and p.event_type is not None
    ]
    with (OUT / "events.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "council_name",
                "event_type",
                "event_date",
                "financial_year",
                "amount_gbp_m",
                "verification",
                "source_url",
            ]
        )
        for code, year, etype in events:
            fy = str(year) if etype == "efs" else ""
            amt = f"{rng.uniform(5, 60):.1f}" if etype == "efs" else ""
            w.writerow(
                [by_code[code], etype, event_date(year, etype), fy, amt, "primary", "synthetic"]
            )
    print(f"wrote {len(councils)} councils, {len(rows)} finance rows, {len(events)} events")


if __name__ == "__main__":
    main()
