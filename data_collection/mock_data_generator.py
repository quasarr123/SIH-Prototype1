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
  * The two sources differ slightly in their quoted price (small
    site-to-site variance), like real OTAs do.
  * A market-wide trend is layered on top across the search-date
    range: fares drift up (or down) day over day, so the Airfare
    Index computed later actually moves away from 100 — otherwise
    every demo would show a flat, boring index.
  * Random day-to-day noise on top of all of the above.
  * For each (search date, route) combination, several travel dates
    are searched (7, 14, and 30 days out), matching how a real fare
    tracker would repeatedly check a spread of upcoming departure
    dates.
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config import ROUTES, ROUTE_BASE_FARE, AIRLINES, AIRLINE_MULTIPLIER, SOURCES  # noqa: E402

# How many days of "search history" to simulate.
DEFAULT_HISTORY_DAYS = 30

# How many days out (from the search date) travel dates are checked.
TRAVEL_DATE_OFFSETS = [7, 14, 30]

# Overall market trend across the simulated history: total percentage
# drift from the first search day to the last (e.g. +6 means fares
# drift up ~6% end-to-end, with daily noise on top).
MARKET_TREND_PCT = 6.0

# Site-to-site price variance (each source randomly quotes within
# +/- this fraction of the "true" computed fare).
SOURCE_VARIANCE = 0.03

# Day-to-day random noise applied per quote.
DAILY_NOISE = 0.04

random.seed(42)  # deterministic sample dataset for reproducibility


def _trend_multiplier(day_index: int, total_days: int) -> float:
    """Smooth market-wide drift from 1.0 up/down to (1 + MARKET_TREND_PCT/100)."""
    if total_days <= 1:
        return 1.0
    progress = day_index / (total_days - 1)
    return 1.0 + (MARKET_TREND_PCT / 100.0) * progress


def generate_mock_fares(history_days: int = DEFAULT_HISTORY_DAYS) -> List[Dict[str, Any]]:
    """
    Build a full list of mock fare records covering `history_days` of
    simulated daily searches, across all routes, all airlines, and
    both sources.
    """
    records: List[Dict[str, Any]] = []
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

                        records.append(
                            {
                                "source": source,
                                "airline": airline,
                                "origin": origin,
                                "destination": destination,
                                "travel_date": travel_date.isoformat(),
                                "search_datetime": search_dt.isoformat(),
                                "fare_price": final_price,
                            }
                        )

    return records


if __name__ == "__main__":
    data = generate_mock_fares()
    print(f"Generated {len(data)} mock fare records.")
    print(data[0])
