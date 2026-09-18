-- schema.sql
-- Raw fare-quote table. Each row is ONE price observation:
-- a specific source's quoted price, for a specific airline,
-- for a specific route + travel date, at the moment it was searched.
--
-- This is intentionally a single flat "fact" table (a classic
-- time-series / event-log design) because:
--   1. It matches exactly how the data is collected (one row per scrape).
--   2. All the analytics (route avg, airline avg, index, trend) are
--      just GROUP BY / window aggregations over this one table.
--
-- Phase 3 / Phase 4 (see docs/methodology.md):
--   * The capture-spec columns (lead_time_days, booking_class,
--     fare_type) guarantee every row prices the SAME "item
--     specification", which is what makes period-over-period
--     comparison statistically valid for CPI.
--   * The audit-trail columns (scrape_id, raw_fare_value, source_url,
--     validation_status, flag_reason) make every stored fare traceable
--     to its source, its exact raw text, and whether it passed the
--     Phase-4 quality checks.

CREATE TABLE IF NOT EXISTS fares (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    source             TEXT    NOT NULL,   -- website the fare was collected from
    airline            TEXT    NOT NULL,
    origin             TEXT    NOT NULL,   -- IATA code, e.g. 'DEL'
    destination        TEXT    NOT NULL,   -- IATA code, e.g. 'BOM'
    travel_date        TEXT    NOT NULL,   -- date the flight departs, 'YYYY-MM-DD'
    search_datetime    TEXT    NOT NULL,   -- when the price was observed, ISO timestamp
    fare_price         REAL    NOT NULL,   -- price in INR
    -- Phase 3: like-for-like capture specification
    lead_time_days     INTEGER,            -- booking lead: (travel_date - search_date) in days
    booking_class      TEXT    DEFAULT 'economy',
    fare_type          TEXT    DEFAULT 'non_refundable',
    -- Phase 4: audit trail
    scrape_id          TEXT,               -- identifier for the collection run that produced this row
    raw_fare_value     TEXT,               -- exact raw scraped text before parsing (e.g. 'Rs 6,442')
    source_url         TEXT,               -- URL / API call the fare was observed at
    validation_status  TEXT    DEFAULT 'pending',  -- 'pending' | 'passed' | 'flagged'
    flag_reason        TEXT,               -- human-readable reasons when flagged (semicolon-joined)
    created_at         TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- One row per collection run (Phase 4 audit trail on the run itself).
CREATE TABLE IF NOT EXISTS scrape_runs (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    run_datetime      TEXT NOT NULL DEFAULT (datetime('now')),
    scrape_id         TEXT,               -- links fares.scrape_id to this run
    source            TEXT,
    origin            TEXT,
    destination       TEXT,
    travel_date       TEXT,
    status            TEXT,               -- 'completed' | 'partial' | 'failed'
    records_expected  INTEGER DEFAULT 0,
    records_found     INTEGER DEFAULT 0,
    notes             TEXT
);

CREATE INDEX IF NOT EXISTS idx_fares_route
    ON fares (origin, destination);

CREATE INDEX IF NOT EXISTS idx_fares_search_date
    ON fares (search_datetime);

CREATE INDEX IF NOT EXISTS idx_fares_airline
    ON fares (airline);

CREATE INDEX IF NOT EXISTS idx_fares_scrape_id
    ON fares (scrape_id);

CREATE INDEX IF NOT EXISTS idx_runs_scrape_id
    ON scrape_runs (scrape_id);