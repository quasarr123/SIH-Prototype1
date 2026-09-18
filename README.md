# India Domestic Airfare Price Index — POC

A proof-of-concept system that tracks airline ticket prices across popular
Indian domestic routes and computes an **Airfare Price Index** (a CPI-style
metric for flights) showing whether fares are trending cheaper or more
expensive — visualized in a Streamlit dashboard.

Built as a prototype for **SIH 2026 (Smart India Hackathon)**,
*Problem Statement 26056: Development of a Real-time Airfare Price Index for
India through Automated Web Scraping … for Augmentation of the Consumer
Price Index (CPI).*

---

## 🧠 What this project does

```
Flight fare data → Data storage → Data cleaning → Baseline calculation → Airfare Index → Dashboard
```

Every stage of the pipeline is implemented and runnable end-to-end with two
interchangeable data sources that feed the exact same
storage → cleaning → index → dashboard pipeline:

| Data source | Description |
|---|---|
| 🎭 **Mock data** (default) | ~12,600 simulated fare records across 7 routes / 5 airlines / 3 sources / 4 booking leads. Zero setup, reproducible, great for demoing the index. |
| ✈️ **Live Ixigo scrape** (`--live`) | Real fares scraped from Ixigo via Selenium, matching the exact same data shape. Prototype for SIH — see [legal note](#-legal-note). |

---

## 📁 Project structure

```
airfare-index-poc/
├── config.py                        # routes, weights, capture spec, scope, index settings
├── main.py                          # pipeline orchestrator (mock or live)
├── requirements.txt
├── run.sh                           # macOS/Linux one-click runner
├── run.bat                          # Windows one-click runner
├── run_app.sh                       # ONE-COMMAND: scrape -> update DB -> dashboard (macOS/Linux)
├── run_app.bat                      # ONE-COMMAND launcher (Windows)
├── docs/
│   └── methodology.md               # full CPI methodology (base period, basket, capture rule, quality, Laspeyres)
├── data/
│   ├── airfare.db                   # SQLite database (auto-created)
│   └── sample_fares.csv             # exported cleaned sample dataset
├── data_collection/
│   ├── collectors.py                # BaseFareCollector interface + stubs
│   ├── ixigo_scraper.py             # LIVE Selenium scraper for Ixigo
│   └── mock_data_generator.py       # realistic mock fare generator
├── database/
│   ├── schema.sql                   # SQLite table definition (+ audit columns / scrape_runs)
│   └── db.py                        # init / insert / query / audit helpers
├── processing/
│   ├── cleaning.py                  # cleaning + data-quality layer (outliers, stale, validation, capture spec)
│   └── index_calculator.py          # weighted Laspeyres Airfare Index math
└── dashboard/
    └── app.py                       # Streamlit dashboard
```

---

## 🚀 Quick start

### ⭐ One command for everything (scrape → update → dashboard)

```bash
./run_app.sh        # macOS / Linux  — scrapes Ixigo live, updates the DB, opens the dashboard
run_app.bat         # Windows

# Don't want to scrape / no network? Regenerate mock data instead:
USE_MOCK=1 ./run_app.sh
```

This runs the fare collector, refreshes the database, then launches the
dashboard at http://localhost:8501. If the live scrape finds nothing it keeps
existing data and still opens the app (`--tolerant`); if the database was
wiped and the scrape comes back empty, it auto-seeds representative mock
fares so the demo always runs.

### Option A — one-click pipeline script

```bash
# macOS / Linux
./run.sh

# Windows
run.bat
```

### Option B — manual

```bash
# 1. Create + activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate mock data, compute the index, print the report
python main.py
```

### Run with real Ixigo fares (optional)

```bash
python main.py --live                  # all 7 routes, 15 days out (capture-spec lead)
python main.py --live --date 2025-08-15
python main.py --live --refresh        # wipe the DB first
IXIGO_HEADLESS=1 python main.py --live # headless Chrome, no visible window
python main.py --live --tolerant       # don't exit if the scrape is empty
```

### Launch the dashboard

```bash
streamlit run dashboard/app.py         # opens http://localhost:8501
```

The sidebar has a **"Scrape & update data now"** button that re-collects live
fares and reloads the dashboard without leaving it.

### 🕵️ Browser fingerprint hygiene
Every live scrape presents as a **first-time ordinary visitor**:
- a brand-new ephemeral Chrome profile (deleted afterwards) — no cookie /
  fingerprint carry-over between runs,
- a **rotating user-agent** from a small pool instead of one static string,
- automation flags disabled (`navigator.webdriver` masked via CDP,
  `enable-automation`/`AutomationControlled` stripped),
- human-ish timing jitter on render/scroll waits.

This reduces the odds the OTA recognises the scrapes as a single recurring
automated visitor. It is *not* full anti-bot evasion — a production index
should use an official API/licensed feed (see the legal note below).

---

## 📊 Output

Running the pipeline:

1. Creates `data/airfare.db` (SQLite) and populates the `fares` table — plus
   a `scrape_runs` audit table (Phase 4).
2. Cleans the data, **runs the quality layer** (outlier / stale detection),
   and **persists the per-row validation verdict** back to the DB (audit trail).
3. Computes the **CPI-compatible weighted Laspeyres Airfare Index** and
   prints a summary report (with the flag summary for transparency).
4. Exports `data/sample_fares.csv` (cleaned, quality-passed dataset).

The dashboard adds interactive route/airline/date filters, the headline
weighted index, route contributions, per-route and per-airline comparisons,
a methodology explainer, and price/index trend charts.

---

## 🧮 How the Airfare Index works

The index is a **modified Laspeyres-style aggregate**, built to the same
statistical rules MoSPI uses for CPI sub-indices:

```text
I_t = ( Σ_r  w_r · ( P_rt / P_r0 ) ) × 100
```

- **`r`** — each route in the fixed basket
- **`w_r`** — route weight = passenger-volume share (Σw = 1)
- **`P_r0`** — base-period like-for-like fare (earliest `BASELINE_WINDOW_DAYS`
  search days; index = 100 there)
- **`P_rt`** — current like-for-like fare (latest `CURRENT_WINDOW_DAYS` days)
- **100** → unchanged · **>100** → fares rose · **<100** → fares fell

Fares are *like-for-like* (fixed capture spec: economy, non-refundable,
15-day booking lead ±3) and *quality-validated* (flagged outliers and stale
quotes are excluded). Full methodology: [docs/methodology.md](docs/methodology.md).

The same formula is computed **overall** (route-weighted), **per-route**
(showing each route's weight & point contribution), and as a **time series**
(index recomputed for every search date against one fixed base period).

All settings live in `config.py`:

| Setting | Default |
|---|---|
| Routes (pilot basket) | DEL–BOM, DEL–BLR, BOM–BLR, DEL–MAA, BOM–MAA, DEL–CCU, BLR–HYD |
| Route weights (passenger shares) | 20 / 18 / 15 / 13 / 13 / 11 / 10 % |
| Airlines | IndiGo, Air India, SpiceJet, Vistara, Akasa Air |
| Sources | SkyFareHub, TripEase (mock) + Ixigo (live) |
| Capture spec | economy · non-refundable · lead 15 days (±3) |
| Base period | earliest 7 search days (`BASELINE_WINDOW_DAYS`) |
| Current window | latest 3 search days (`CURRENT_WINDOW_DAYS`) |

---

## 🛠 Tech stack

- **Python 3.10+**
- **pandas** — data transformation & aggregation
- **Selenium + webdriver-manager** — live Ixigo scraping
- **SQLite** — zero-setup storage (swappable for PostgreSQL)
- **Streamlit + Plotly** — interactive dashboard

---

## 🌱 Why mock data by default?

Most Indian flight-booking sites (MakeMyTrip, Yatra, Cleartrip, Ixigo…) may
disallow automated scraping in their Terms of Service, and official fare
feeds usually require paid/licensed access (airline partner APIs, GDS like
Amadeus/Sabre). So the project defaults to a **deterministic mock generator**
that produces realistic data — route-specific base fares, per-airline price
multipliers, cross-OTA variance, market drift, and booking-lead-time
discounts — in the *exact same shape* a real collector would.

The **Ixigo scraper** ships as a working Selenium prototype for the SIH
submission: it hits the site's real results URL, waits for the JS-rendered
flight cards, and parses fares anchored on stable `data-testid` attributes.

### ⚖️ Legal note

Use the live scraper only where you have permission. For production, prefer
an official API or a licensed data feed. This code is an educational/SIH
prototype.

---

## 🧰 Collector interface (extending the system)

Every data source implements `BaseFareCollector.fetch(origin, destination, travel_date)`
returning dicts of the form:

```python
{
    "source": "Ixigo",
    "airline": "IndiGo",
    "origin": "DEL",
    "destination": "BOM",
    "travel_date": "2026-09-16",
    "search_datetime": "2026-09-15T11:30:00",
    "fare_price": 6442.0,
    # Phase 3 — like-for-like capture specification
    "lead_time_days": 15,             # = travel_date − search_date
    "booking_class": "economy",
    "fare_type": "non_refundable",
    # Phase 4 — audit trail
    "scrape_id": "2424a4c1-...",     # this collection run's id
    "raw_fare_value": "Rs 6,442",    # exact scraped text before parsing
    "source_url": "https://www.ixigo.com/search/result/flight?...",
}
```

Add a new OTA/airline by implementing `fetch()` in a new collector class and
registering it — no downstream code changes needed.

---

## 🧭 Roadmap to production

- [x] Data acquisition (mock + Ixigo prototype)
- [x] Storage, cleaning, index calculation
- [x] CPI methodology (base period, route basket & weights, capture spec,
      quality layer, Laspeyres aggregation — see `docs/methodology.md`)
- [x] Streamlit dashboard
- [ ] More compliant sources (official APIs / licensed feeds)
- [ ] Scheduled collection (cron / Airflow)
- [ ] PostgreSQL instead of SQLite
- [ ] Dashboard authentication
- [ ] REST/GraphQL API for MoSPI-style integration

---

## 🗂 License

[MIT](LICENSE) — free to use for educational and hackathon purposes.