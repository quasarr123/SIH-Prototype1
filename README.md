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
| 🎭 **Mock data** (default) | ~6,300 realistic simulated fare records across 7 routes / 5 airlines / 3 sources. Zero setup, reproducible, great for demoing the index. |
| ✈️ **Live Ixigo scrape** (`--live`) | Real fares scraped from Ixigo via Selenium, matching the exact same data shape. Prototype for SIH — see [legal note](#-legal-note). |

---

## 📁 Project structure

```
airfare-index-poc/
├── config.py                        # routes, airlines, sources, index-window settings
├── main.py                          # pipeline orchestrator (mock or live)
├── requirements.txt
├── run.sh                           # macOS/Linux one-click runner
├── run.bat                          # Windows one-click runner
├── data/
│   ├── airfare.db                   # SQLite database (auto-created)
│   └── sample_fares.csv             # exported cleaned sample dataset
├── data_collection/
│   ├── collectors.py                # BaseFareCollector interface + stubs
│   ├── ixigo_scraper.py             # LIVE Selenium scraper for Ixigo
│   └── mock_data_generator.py       # realistic mock fare generator
├── database/
│   ├── schema.sql                   # SQLite table definition
│   └── db.py                        # init / insert / query helpers
├── processing/
│   ├── cleaning.py                  # data cleaning pipeline
│   └── index_calculator.py          # Airfare Index math + analytics
└── dashboard/
    └── app.py                       # Streamlit dashboard
```

---

## 🚀 Quick start

### Option A — one-click script

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
python main.py --live                  # all 7 routes, next travel day
python main.py --live --date 2025-08-15
python main.py --live --refresh        # wipe the DB first
IXIGO_HEADLESS=1 python main.py --live # headless Chrome, no visible window
```

### Launch the dashboard

```bash
streamlit run dashboard/app.py         # opens http://localhost:8501
```

---

## 📊 Output

Running the pipeline:

1. Creates `data/airfare.db` (SQLite) and populates the `fares` table.
2. Cleans the data (drops missing/invalid prices, bounds-checks, dedupes).
3. Computes the **Airfare Index** and prints a summary report.
4. Exports `data/sample_fares.csv` (cleaned dataset).

The dashboard adds interactive route/airline/date filters, a headline index
metric, per-route and per-airline comparisons, and price/index trend charts.

---

## 🧮 How the Airfare Index works

```
Airfare Index = (Current Average Fare / Baseline Average Fare) × 100
```

- **Baseline Average Fare** — average fare over the *earliest* N distinct
  search dates (`BASELINE_WINDOW_DAYS`, default 7).
- **Current Average Fare** — average fare over the *latest* M distinct
  search dates (`CURRENT_WINDOW_DAYS`, default 3).
- **100** → unchanged · **>100** → fares rose · **<100** → fares fell.

The same formula is computed **overall**, **per-route**, and as a **time
series** (index recomputed for every search date against one fixed baseline)
so the dashboard can show how the index itself has moved.

All settings live in `config.py`:

| Setting | Default |
|---|---|
| Routes | DEL–BOM, DEL–BLR, BOM–BLR, DEL–MAA, BOM–MAA, DEL–CCU, BLR–HYD |
| Airlines | IndiGo, Air India, SpiceJet, Vistara, Akasa Air |
| Sources | SkyFareHub, TripEase (mock) + Ixigo (live) |
| Baseline window | 7 days |
| Current window | 3 days |

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
}
```

Add a new OTA/airline by implementing `fetch()` in a new collector class and
registering it — no downstream code changes needed.

---

## 🧭 Roadmap to production

- [x] Data acquisition (mock + Ixigo prototype)
- [x] Storage, cleaning, index calculation
- [x] Streamlit dashboard
- [ ] More compliant sources (official APIs / licensed feeds)
- [ ] Scheduled collection (cron / Airflow)
- [ ] PostgreSQL instead of SQLite
- [ ] Dashboard authentication
- [ ] REST/GraphQL API for MoSPI-style integration

---

## 🗂 License

[MIT](LICENSE) — free to use for educational and hackathon purposes.