# Backtest report

Horizon 2 years, top-5 flagged per year, evaluation years: 2020, 2021, 2022.

| Model | Precision@k | Recall@k | Events caught | Median lead (days) |
|---|---|---|---|---|
| rules_v1 | 0.53 | 0.57 | 6 of 9 | 400 |
| reserves_only | 0.47 | 0.50 | 5 of 9 | 354 |
| hgb | 0.40 | 0.43 | 6 of 9 | 350 |

Skipped years:

- 2016: fewer than 3 training years
- 2017: fewer than 3 training years
- 2018: fewer than 3 training years
- 2019: fewer than 3 training years
- 2023: label window not yet observed
- 2024: label window not yet observed
- 2025: label window not yet observed

## Watchlist for 2025 (outcome not yet known)

- **rules_v1**: Elmhollow Council (67.5), Stonemere Council (64.5), Fernford Council (64.3), Thornvale Council (63.6), Uptonford Council (61.2)
- **reserves_only**: Stonemere Council (78.6), Elmhollow Council (75.0), Northmere Council (75.0), West Synthetic Shire (71.4), Fernford Council (71.4)
- **hgb**: Thornvale Council (4.8), Ivyvale Council (2.3), Hartmere Council (2.1), Quarrymere Council (1.8), Fernford Council (1.3)

Precision@k is the share of flagged councils that went on to an event within the
horizon. Recall@k is the share of those events that were flagged. Lead time counts
from the decision date of the earliest flag to the event.
