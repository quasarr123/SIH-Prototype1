"""
data_collection/mock_data_generator.py
----------------------------------------
Generates realistic mock fare-search data, in the exact same record
shape a real collector (see collectors.py) would produce. This is
what powers the POC since live scraping is out of scope (ToS
restrictions on Indian travel sites).

Simulated behaviour, to make the resulting Airfare Index meaningful:
  * Each route has a realistic base fare (config.ROUTE_BASE_FARE).
  * Airlines price at a consistent multiplier of the base fare
    (config.AIRLINE_MULTIPLIER) — e.g. Vistara > IndiGo.
  * The two sources+Ixigo differ slightly in their quoted price (small
    site-to-site variance), like real OTAs do.
  * A market-wide trend is layered on top across the search-date
    range: fares drift up (or down) day over day, so the Airfare
    Index computed later actually moves away from 100 — otherwise
    every demo would show a flat, boring index.
  * Random day-to-day noise on top of all of the above.
  * For each (search date, route) combination, several travel dates
    are searched (Phase 3 capture spec): the "reference" search is
    made exactly CAPTURE_SPEC['lead_time_days'] days before departure
    (like-for-like), with other lead times recorded as the surrounding
    observation spread a real fare tracker would see. Every record is
    tagged with its capture-spec fields (booking_class, fare_type,
    lead_time_days) so downstream like-for-like filtering can be done
    explicitly instead of capturing "any" fare.
  * Phase 4: a small, deterministic set of data-quality anomalies
    (absurd prices + cached/stale repeats) is injected so the
    cleaning/validation layer has realistic material to flag — the
    audit trail is part of the demo.
"""

import random
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import (  # noqa: E402
    ROUTES,
    ROUTE_BASE_FARE,
    AIRLINES,
    AIRLINE_MULTIPLIER,
    SOURCES,
    CAPTURE_SPEC,
    OUTLIER_HARD_MAX,
)

# How many days of "search history" to simulate.
DEFAULT_HISTORY_DAYS = 30

# How many days out (from the search date) travel dates are checked.
# The capture spec's reference lead time (15 days) is included so the
# "exact" like-for-like quote exists; the others are the surrounding
# observation spread.
TRAVEL_DATE_OFFSETS = [7, 14, CAPTURE_SPEC["lead_time_days"], 30]

# Overall market trend across the simulated history: total percentage
# drift from the first search day to the last (e.g. +6 means fares
# drift up ~6% end-to-end, with daily noise on top).
MARKET_TREND_PCT = 6.0

# Site-to-site price variance (each source randomly quotes within
# +/- this fraction of the "true" computed fare).
SOURCE_VARIANCE = 0.03

# Day-to-day random noise applied per quote.
DAILY_NOISE = 0.04

# Anomaly injection (Phase 4 demo material). Small deterministic counts
# so the quality layer has something to flag without swamping the data.
OUTLIER_COUNT = 12                 # absurd prices (hard-band / IQR)
STALE_REPEAT_COUNT = 6             # (route, airline, source, lead) chains with a cached-price repeat

random.seed(42)  # deterministic sample dataset for reproducibility


def _trend_multiplier(day_index: int, total_days: int) -> float:
    """Smooth market-wide drift from 1.0 up/down to (1 + MARKET_TREND_PCT/100)."""
    if total_days <= 1:
        return 1.0
    progress = day_index / (total_days - 1)
    return 1.0 + (MARKET_TREND_PCT / 100.0) * progress


def generate_mock_fares(
    history_days: int = DEFAULT_HISTORY_DAYS,
    inject_anomalies: bool = True,
) -> List[Dict[str, Any]]:
    """
    Build a full list of mock fare records covering `history_days` of
    simulated daily searches, across all routes, all airlines, and all
    sources. Every record carries the Phase-3 capture-spec fields and
    the Phase-4 audit fields (scrape_id, raw_fare_value, source_url).

    If `inject_anomalies` is True, a seeded number of outlier prices and
    stale repeats are baked in so the data-quality layer has realistic
    material to flag.
    """
    scrape_id = str(uuid.uuid4())
    records: List[Dict[str, Any]] = []
    raw: List[Dict[str, Any]] = []  # same rows but with plain prices (pre-format)

    today = datetime.now().date()
    start_day = today - timedelta(days=history_days - 1)

    for day_index in range(history_days):
        search_date = start_day + timedelta(days=day_index)
        trend = _trend_multiplier(day_index, history_days)

        for origin, destination in ROUTES:
            base_fare = ROUTE_BASE_FARE[(origin, destination)]

            for travel_offset in TRAVEL_DATE_OFFSETS:
                travel_date = search_date + timedelta(days=travel_offset)
                # Fares are typically a bit cheaper the further out you book.
                lead_time_discount = 1.0 - min(travel_offset, 45) * 0.002

                for airline in AIRLINES:
                    airline_price = (
                        base_fare
                        * AIRLINE_MULTIPLIER[airline]
                        * trend
                        * lead_time_discount
                    )

                    for source in SOURCES:
                        noise = random.uniform(-DAILY_NOISE, DAILY_NOISE)
                        site_variance = random.uniform(-SOURCE_VARIANCE, SOURCE_VARIANCE)
                        final_price = airline_price * (1 + noise + site_variance)
                        final_price = round(max(final_price, 1500), 2)  # sane floor

                        search_dt = datetime.combine(
                            search_date, datetime.min.time()
                        ) + timedelta(
                            hours=random.randint(6, 22), minutes=random.randint(0, 59)
                        )

                        raw.append(
                            {
                                "source": source,
                                "airline": airline,
                                "origin": origin,
                                "destination": destination,
                                "travel_date": travel_date.isoformat(),
                                "search_datetime": search_dt.isoformat(),
                                "fare_price": final_price,
                                "lead_time_days": travel_offset,
                                "booking_class": CAPTURE_SPEC["booking_class"],
                                "fare_type": CAPTURE_SPEC["fare_type"],
                            }
                        )

    records = _finalize_records(raw, scrape_id)

    if inject_anomalies:
        records = _inject_outliers(records)
        records = _inject_stale_repeats(records)

    return records


def _finalize_records(raw: List[Dict[str, Any]], scrape_id: str) -> List[Dict[str, Any]]:
    """Attach the audit fields (scrape_id / raw_fare_value / source_url)."""
    records: List[Dict[str, Any]] = []
    for r in raw:
        price = r["fare_price"]
        records.append(
            {
                **r,
                "scrape_id": scrape_id,
                "raw_fare_value": f"Rs {price:,.0f}",
                "source_url": (
                    f"https://mock.{r['source'].lower()}.example/search"
                    f"?from={r['origin']}&to={r['destination']}"
                    f"&date={r['travel_date']}"
                ),
            }
        )
    return records


def _inject_outliers(records: List[Dict[str, Any]], count: int = OUTLIER_COUNT) -> List[Dict[str, Any]]:
    """
    Corrupt `count` random rows so their price is absurdly high (clearly
    a mis-parse / scrape error). These exercise the Phase-4 detection.
    """
    if not records:
        return records
    chosen = random.sample(range(len(records)), min(count, len(records)))
    for idx in chosen:
        rec = records[idx]
        rec["fare_price"] = round(OUTLIER_HARD_MAX * random.uniform(2.0, 4.0), 2)
        rec["raw_fare_value"] = f"Rs {rec['fare_price']:,.0f}"
    return records


def _inject_stale_repeats(records: List[Dict[str, Any]], count: int = STALE_REPEAT_COUNT) -> List[Dict[str, Any]]:
    """
    Force `count` (route, airline, source, lead) chains to repeat the
    previous day's fare price — simulating a cached/stale page.
    """
    if not records:
        return records

    def key_of(r: Dict[str, Any]) -> tuple:
        return (
            r["airline"], r["source"], r["origin"],
            r["destination"], r["lead_time_days"],
        )

    by_date: Dict[str, Dict[tuple, Dict[str, Any]]] = {}
    for rec in records:
        by_date.setdefault(rec["search_datetime"][:10], {})[key_of(rec)] = rec

    dates = sorted(by_date.keys())
    pool = sorted({key_of(r) for r in records})
    random.shuffle(pool)

    injected = 0
    for _key in pool:
        # pick a mid-history day so both the prior and next day exist
        for i in range(1, len(dates) - 1):
            prev_rec = by_date[dates[i - 1]].get(_key)
            cur_rec = by_date[dates[i]].get(_key)
            if prev_rec is None or cur_rec is None:
                continue
            keep = prev_rec["fare_price"]
            cur_rec["fare_price"] = keep
            cur_rec["raw_fare_value"] = f"Rs {keep:,.0f}"
            injected += 1
            break
        if injected >= count:
            break

    return records


if __name__ == "__main__":
    data = generate_mock_fares()
    print(f"Generated {len(data)} mock fare records.")
    print(data[0])