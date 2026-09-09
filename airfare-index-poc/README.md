# India Domestic Airfare Price Index — POC

A proof-of-concept system that tracks airline ticket prices over time
across popular Indian domestic routes and calculates an **Airfare
Index** showing whether fares are trending cheaper or more expensive,
visualized in a Streamlit dashboard.

## What this POC demonstrates

```
Flight fare data --> Data storage --> Data cleaning -->
Baseline calculation --> Airfare Index --> Dashboard visualization
```

Every stage of that pipeline is implemented and runnable. Live
scraping of real booking sites is **not** performed — see
[Why mock data?](#why-mock-data) — but the code is structured so a
real, compliant data source can be plugged in later with no changes
to storage, cleaning, index calculation, or the dashboard.

## Project structure

```
airfare-index-poc/
├── config.py                        # routes, airlines, sources, index-window settings
├── main.py                          # runs the full pipeline end-to-end
├── requirements.txt
├── data/
│   ├── airfare.db                   # SQLite database (created on first run)
│   └── sample_fares.csv             # exported sample dataset (cleaned)
├── data_collection/
│   ├── collectors.py                # collector interface + stubs for real scraping
│   └── mock_data_generator.py       # generates realistic mock fare data
├── database/
│   ├── schema.sql                   # SQLite table definition
│   └── db.py                        # init / insert / query functions
├── processing/
│   ├── cleaning.py                  # data cleaning pipeline
│   └── index_calculator.py          # Airfare Index + all derived analytics
└── dashboard/
    └── app.py                       # Streamlit dashboard
```

## Setup

```bash
cd airfare-index-poc
pip install -r requirements.txt
```

## Running it

**1. Generate the dataset and populate the database:**

```bash
python main.py
```

This creates `data/airfare.db`, generates ~30 days of simulated daily
fare searches across all 7 routes / 5 airlines / 2 sources (~6,300
records), stores them, cleans them, computes the Airfare Index, prints
a summary to the console, and exports `data/sample_fares.csv`.

To wipe and regenerate fresh data: `python main.py --refresh`

**2. Launch the dashboard:**

```bash
streamlit run dashboard/app.py
```

Opens at `http://localhost:8501`.

## Data model

Every fare observation is one row in the `fares` table:

| Column          | Meaning                                      |
|-----------------|-----------------------------------------------|
| source          | Website the fare was collected from           |
| airline         | Operating airline                             |
| origin / destination | Route (IATA airport codes)               |
| travel_date     | Date the flight departs                       |
| search_datetime | When the price was observed                   |
| fare_price      | Quoted price (INR)                            |

**Routes tracked (7):** DEL–BOM, DEL–BLR, BOM–BLR, DEL–MAA, BOM–MAA,
DEL–CCU, BLR–HYD

**Airlines tracked (5):** IndiGo, Air India, SpiceJet, Vistara, Akasa Air

**Sources (2):** `SkyFareHub`, `TripEase` — fictional placeholder
names for this POC's mock data (see below).

## The Airfare Index

```
Airfare Index = (Current Average Fare / Baseline Average Fare) x 100
```

- **Baseline Average Fare** — the average fare across the *earliest*
  N distinct search dates in the data (the "initial observation
  period"). N is `BASELINE_WINDOW_DAYS` in `config.py` (default 7).
- **Current Average Fare** — the average fare across the *latest* M
  distinct search dates. M is `CURRENT_WINDOW_DAYS` in `config.py`
  (default 3).
- **100** → fares unchanged from baseline · **>100** → fares risen ·
  **<100** → fares fallen.

The same formula is applied at three granularities:
- **Overall** (`compute_overall_index`) — across all routes/airlines/sources.
- **Per route** (`route_wise_index`) — used to compare route-wise inflation.
- **Over time** (`index_trend_over_time`) — the index recomputed for
  every search date against the *same fixed baseline*, so you can see
  the index trend line rather than a single snapshot number.

Additional analytics computed in `processing/index_calculator.py`:
route-wise average fare, airline-wise average fare, % change from
baseline, cheapest/most expensive route, and daily price trend.

## Dashboard

The Streamlit dashboard (`dashboard/app.py`) shows:

1. Overall Airfare Index (headline metric)
2. Current average airfare
3. Percentage change from baseline
4. Route-wise price comparison (table + grouped bar chart)
5. Price trend graph (both raw average fare and the index itself, over time)
6. Airline-wise comparison (table + bar chart)
7. Cheapest route (callout)
8. Most expensive route (callout)
9. Filters for route, airline, and travel date range (sidebar) — the
   Airfare Index and every chart recompute live against the filtered data.

## Why mock data?

Most Indian flight-booking sites (MakeMyTrip, Yatra, Cleartrip, etc.)
explicitly disallow automated scraping in their Terms of Service, and
official fare data is normally only available via paid/licensed APIs
(an airline partner API, or a GDS like Amadeus/Sabre). Scraping them
without permission would violate those terms, so this POC uses a
**mock data generator** (`data_collection/mock_data_generator.py`)
that produces data in the exact same shape a real collector would.

The mock generator isn't random noise — it simulates realistic
airfare behaviour so the resulting index is meaningful for a demo:
- Each route has a realistic base fare, and each airline prices at a
  consistent multiplier of it (e.g. Vistara priced above IndiGo).
- The two sources quote slightly different prices for the same
  flight, like real OTAs do.
- A market-wide trend drifts fares up over the simulated month, plus
  day-to-day random noise, so the index visibly moves away from 100.
- Fares searched further in advance of travel are modestly cheaper,
  mimicking real booking-lead-time discounts.

## Making it production-ready later

`data_collection/collectors.py` defines a `BaseFareCollector`
interface — every source (mock or real) returns fare records in the
identical shape, so nothing downstream needs to change. To go live:

1. Get a licensed data feed or written scraping permission from a
   provider (an airline API, an OTA partner API, or a GDS).
2. Implement `fetch()` on a new collector class using that provider —
   the file includes commented Playwright and BeautifulSoup sketches
   showing exactly where that code would go.
3. Register the class in `ACTIVE_COLLECTORS` and call it from a
   scheduled job (e.g. cron / Airflow) instead of
   `mock_data_generator.generate_mock_fares()`.
4. Swap `database/db.py`'s SQLite connection for PostgreSQL — every
   other module only uses plain SQL/pandas, so this is a localized
   change.

## Known limitations (expected for a POC)

- Uses SQLite, not PostgreSQL (swap is straightforward — see above).
- No scheduled/automated data collection (would need cron/Airflow in production).
- No authentication on the dashboard.
- Mock dataset only — not real-time market prices.
- Baseline/current window sizes are simple day-count heuristics, not
  a formally validated statistical method (fine for a POC; a
  production version might use category-adjusted baselines by
  route + cabin class + booking-lead-time bucket).
