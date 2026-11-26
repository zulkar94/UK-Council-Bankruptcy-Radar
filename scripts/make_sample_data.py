"""Generate the synthetic sample panel in data/sample/. Deterministic (seed 42).

All councils, codes and figures are invented. Codes use a 9xx range so they cannot
collide with real ONS codes. A few distressed councils drift into trouble and then
get an event, and one county splits into two unitaries in 2021, so every part of
the pipeline is exercised.
"""

from __future__ import annotations

import csv
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "sample"
YEARS = list(range(2018, 2026))  # ending years: 2017-18 .. 2024-25
SPLIT_YEAR = 2022  # first full year for successor unitaries
MARKER_RATE = 0.04  # share of rows given a missing-value marker
rng = random.Random(42)

TIERS = {
    "E06": ("unitary", 8, 260_000),
    "E07": ("district", 10, 18_000),
    "E08": ("metropolitan", 5, 520_000),
    "E09": ("london_borough", 5, 330_000),
}
DISTRESSED = {"E06000903", "E07000905", "E08000902", "E09000904"}
COUNTY, SUCC_A, SUCC_B = "E10000901", "E06000951", "E06000952"


def fy_label(y: int) -> str:
    return f"{y - 1}-{str(y)[2:]}"


PLACES = [
    "Ashvale",
    "Brookmere",
    "Calderford",
    "Dunhollow",
    "Elmstead",
    "Fernleigh",
    "Glenmarsh",
    "Hartwell",
    "Ivybridge Vale",
    "Juniper Cross",
    "Kestrel Bay",
    "Larkhaven",
    "Millbourne",
    "Northcote Fen",
    "Oakhurst",
    "Pennford",
    "Quarrydale",
    "Ravenmoor",
    "Stonebury",
    "Thornwick",
    "Upton Marsh",
    "Westerleigh",
    "Yarrowby",
    "Ambermouth",
    "Birchley",
    "Coldharbour Vale",
    "Dovecliff",
    "Easterholme",
]


def council_rows() -> list[dict[str, str]]:
    rows = []
    places = iter(PLACES)
    for prefix, (_tier, n, _) in TIERS.items():
        for i in range(1, n + 1):
            code = f"{prefix}000{900 + i}"
            rows.append({"ons_code": code, "name": f"{next(places)} Council"})
    rows += [
        {"ons_code": COUNTY, "name": "Synthetic Shire County", "valid_to": "2021-03-31"},
        {"ons_code": SUCC_A, "name": "North Synthetic Shire", "valid_from": "2021-04-01"},
        {"ons_code": SUCC_B, "name": "West Synthetic Shire", "valid_from": "2021-04-01"},
    ]
    for r in rows:
        r.setdefault("tier", "")
        r.setdefault("region", "Synthetic Region")
        r.setdefault("valid_from", "")
        r.setdefault("valid_to", "")
    return rows


def money(x: float) -> str:
    return f"{round(x):,}"


def finance_row(code: str, year: int, scale: float, tier: str, distressed: bool) -> dict[str, str]:
    t = YEARS.index(year) if year in YEARS else 0
    drift = t / (len(YEARS) - 1) if distressed else 0.0
    nre = scale * (1 + 0.04 * t) * rng.uniform(0.95, 1.05)
    reserves_ratio = max(0.02, rng.uniform(0.18, 0.35) - 0.25 * drift)
    unalloc = nre * reserves_ratio * 0.3
    earmarked = nre * reserves_ratio * 0.7
    csp = nre * rng.uniform(0.85, 1.0)
    borrowing = csp * (rng.uniform(0.5, 1.5) + 4.0 * drift)
    commercial = csp * (rng.uniform(0.0, 0.2) + 2.5 * drift)
    interest = borrowing * rng.uniform(0.025, 0.04)
    social = 0.0 if tier == "district" else nre * (rng.uniform(0.45, 0.6) + 0.1 * drift)
    dsg = 0.0 if tier == "district" else nre * rng.uniform(0.0, 0.03) * (1 + 3 * drift)
    row = {
        "ONS code": code,
        "Financial year": fy_label(year),
        "Net revenue expenditure (£000)": money(nre),
        "Unallocated reserves (£000)": money(unalloc),
        "Earmarked reserves (£000)": money(earmarked),
        "DSG deficit (£000)": money(dsg),
        "External borrowing (£000)": money(borrowing),
        "Commercial property (£000)": money(commercial),
        "Interest payable (£000)": money(interest),
        "Core spending power (£000)": money(csp),
        "Social care net spend (£000)": money(social),
    }
    # Sprinkle government-style missing markers so validation has work to do.
    if rng.random() < MARKER_RATE:
        row["Commercial property (£000)"] = rng.choice(["..", "[x]", "-"])
    return row


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    councils = council_rows()
    with (OUT / "councils.csv").open("w", newline="") as f:
        w = csv.DictWriter(
            f, fieldnames=["ons_code", "name", "tier", "region", "valid_from", "valid_to"]
        )
        w.writeheader()
        w.writerows(councils)

    with (OUT / "code_succession.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["old_code", "new_code", "effective", "weight"])
        w.writerow([COUNTY, SUCC_A, "2021-04-01", "0.45"])
        w.writerow([COUNTY, SUCC_B, "2021-04-01", "0.55"])

    rows = []
    for prefix, (tier, n, scale) in TIERS.items():
        for i in range(1, n + 1):
            code = f"{prefix}000{900 + i}"
            for y in YEARS:
                rows.append(finance_row(code, y, scale, tier, code in DISTRESSED))
    for y in YEARS:
        if y < SPLIT_YEAR:
            rows.append(finance_row(COUNTY, y, 700_000, "county", False))
        else:
            rows.append(finance_row(SUCC_A, y, 315_000, "unitary", False))
            rows.append(finance_row(SUCC_B, y, 385_000, "unitary", False))
    with (OUT / "finance_year.csv").open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    names = {c["ons_code"]: c["name"] for c in councils}
    events = [
        ("E06000903", "s114", "2024-11-14", ""),
        ("E07000905", "efs", "2025-02-20", "2026"),
        ("E08000902", "efs", "2025-02-20", "2026"),
        ("E09000904", "s114", "2025-01-09", ""),
        ("E06000905", "efs", "2025-02-20", "2026"),  # no drift: a miss the score should NOT catch
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
        for code, etype, d, fy in events:
            w.writerow(
                [
                    names[code],
                    etype,
                    d,
                    fy,
                    "10.0" if etype == "efs" else "",
                    "primary",
                    "synthetic",
                ]
            )
    print(f"wrote {len(councils)} councils, {len(rows)} finance rows, {len(events)} events")


if __name__ == "__main__":
    main()
