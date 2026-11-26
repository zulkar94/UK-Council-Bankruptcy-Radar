-- Views for Power BI (DirectQuery or Import). Portable SQL: runs on PostgreSQL and SQLite.
-- Model in Power BI as a star: dim_council 1-* each fact view on ons_code.

DROP VIEW IF EXISTS vw_risk_score;
CREATE VIEW vw_risk_score AS
SELECT
    r.ons_code,
    c.name            AS council_name,
    c.tier,
    c.region,
    r.year            AS financial_year_end,
    r.model,
    r.score,
    r.coverage,
    r.top_drivers,
    RANK() OVER (PARTITION BY r.model, r.year, c.tier ORDER BY r.score DESC) AS rank_in_tier
FROM fact_risk_score r
JOIN dim_council c ON c.ons_code = r.ons_code;

DROP VIEW IF EXISTS vw_event;
CREATE VIEW vw_event AS
SELECT
    e.ons_code,
    c.name AS council_name,
    c.tier,
    e.event_type,
    e.event_date,
    e.financial_year AS financial_year_end,
    e.amount_gbp,
    e.verification,
    e.source_url
FROM fact_event e
JOIN dim_council c ON c.ons_code = e.ons_code
WHERE e.verification <> 'unverified';

-- Did the score flag a council before its first distress event? One row per council.
DROP VIEW IF EXISTS vw_early_warning;
CREATE VIEW vw_early_warning AS
WITH first_event AS (
    SELECT ons_code, MIN(event_date) AS first_event_date, MIN(financial_year) AS first_event_fy
    FROM fact_event
    WHERE verification <> 'unverified'
    GROUP BY ons_code
),
prior_scores AS (
    SELECT r.ons_code, r.model, r.year, r.score
    FROM fact_risk_score r
    JOIN first_event f ON f.ons_code = r.ons_code
    -- year Y outturn is published months after March of Y, so only years strictly before
    -- the event's financial year count as knowable in advance
    WHERE r.year < f.first_event_fy
)
SELECT
    f.ons_code,
    c.name AS council_name,
    c.tier,
    f.first_event_date,
    f.first_event_fy,
    p.model,
    MAX(p.score) AS max_prior_score,
    MIN(CASE WHEN p.score >= 75 THEN p.year END) AS first_year_flagged_75
FROM first_event f
JOIN dim_council c ON c.ons_code = f.ons_code
LEFT JOIN prior_scores p ON p.ons_code = f.ons_code
GROUP BY f.ons_code, c.name, c.tier, f.first_event_date, f.first_event_fy, p.model;
