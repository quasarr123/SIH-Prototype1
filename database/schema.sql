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

CREATE TABLE IF NOT EXISTS fares (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT    NOT NULL,   -- website the fare was collected from
    airline         TEXT    NOT NULL,
    origin          TEXT    NOT NULL,   -- IATA code, e.g. 'DEL'
    destination     TEXT    NOT NULL,   -- IATA code, e.g. 'BOM'
    travel_date     TEXT    NOT NULL,   -- date the flight departs, 'YYYY-MM-DD'
    search_datetime TEXT    NOT NULL,   -- when the price was observed, ISO timestamp
    fare_price      REAL    NOT NULL,   -- price in INR
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_fares_route
    ON fares (origin, destination);

CREATE INDEX IF NOT EXISTS idx_fares_search_date
    ON fares (search_datetime);

CREATE INDEX IF NOT EXISTS idx_fares_airline
    ON fares (airline);
