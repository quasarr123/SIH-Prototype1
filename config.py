"""
config.py
---------
Central place for constants shared across the whole POC:
routes tracked, airlines tracked, mock data sources, the
CPI-compatible base period / scope / capture specification,
route passenger-volume weights, and index-window settings.

Keeping these in one file means the scraping module, the
index calculator, and the dashboard all agree on the same
definitions.

Methodology context (SIH 2026 / PS 26056): every constant that
matters for CPI-compatibility lives here so judges, the pipeline,
and MoSPI can all read the statistical assumptions from one place.
See docs/methodology.md for the full written methodology.
"""

from pathlib import Path

# ---------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "airfare.db"
SAMPLE_CSV_PATH = BASE_DIR / "data" / "sample_fares.csv"

# ---------------------------------------------------------------
# 7 popular domestic routes (IATA airport codes)
#
# This is the "pilot subset" of the representative route basket.
# At full scale the basket would be the top N domestic sectors by
# passenger volume from DGCA / AAI traffic statistics (see
# docs/methodology.md, Phase 2); the 7 routes below are that
# basket's demo slice.
# ---------------------------------------------------------------
ROUTES = [
    ("DEL", "BOM"),  # Delhi - Mumbai
    ("DEL", "BLR"),  # Delhi - Bengaluru
    ("BOM", "BLR"),  # Mumbai - Bengaluru
    ("DEL", "MAA"),  # Delhi - Chennai
    ("BOM", "MAA"),  # Mumbai - Chennai
    ("DEL", "CCU"),  # Delhi - Kolkata
    ("BLR", "HYD"),  # Bengaluru - Hyderabad
]

# Rough real-world base fare (INR) used only to make mock data realistic.
ROUTE_BASE_FARE = {
    ("DEL", "BOM"): 5500,
    ("DEL", "BLR"): 6000,
    ("BOM", "BLR"): 4500,
    ("DEL", "MAA"): 6500,
    ("BOM", "MAA"): 5800,
    ("DEL", "CCU"): 6200,
    ("BLR", "HYD"): 3800,
}

# ---------------------------------------------------------------
# Airlines tracked
# ---------------------------------------------------------------
AIRLINES = ["IndiGo", "Air India", "SpiceJet", "Vistara", "Akasa Air"]

# Per-airline pricing tendency relative to the route base fare
# (e.g. full-service carriers price a bit above budget carriers).
AIRLINE_MULTIPLIER = {
    "IndiGo": 1.00,
    "SpiceJet": 0.95,
    "Akasa Air": 0.97,
    "Air India": 1.08,
    "Vistara": 1.15,
}

# ---------------------------------------------------------------
# Data sources
# ---------------------------------------------------------------
# NOTE: These are fictional placeholder source names for the POC's
# mock data. The collection module is architected so a real,
# terms-of-service-compliant source (an official airline/OTA API,
# or a licensed data feed) can be plugged in later without changing
# any downstream code — see data_collection/collectors.py.
SOURCES = ["SkyFareHub", "TripEase", "Ixigo"]

# ---------------------------------------------------------------
# Airfare Index settings
# ---------------------------------------------------------------
# The "base period" (Phase 1): a pinned reference window exactly like
# CPI's fixed base year. MoSPI's CPI uses 2012 = 100; because no
# granular air-travel capture existed for India pre-system, this POC
# sets its own defensible base: the earliest BASE_PERIOD_WINDOW_DAYS
# distinct search dates in the dataset, against which every later
# period is measured. The index equals INDEX_BASE_VALUE (= 100) in
# that base period.
#
# Number of most-recent distinct search dates that make up the
# "baseline" observation period against which the index is measured.
BASELINE_WINDOW_DAYS = 7
BASE_PERIOD_WINDOW_DAYS = BASELINE_WINDOW_DAYS  # alias: same thing
INDEX_BASE_VALUE = 100.0                        # parity with CPI "2012 = 100"

# Number of most-recent distinct search dates considered "current".
CURRENT_WINDOW_DAYS = 3

# ---------------------------------------------------------------
# CPI scope statement (Phase 1)
# ---------------------------------------------------------------
# What this index measures, stated the way a statistical note would.
SCOPE = {
    "included": "domestic economy-class air travel within India, one-way",
    "excluded": [
        "international travel",
        "air cargo",
        "business / first class",
        "charter and private aviation",
        "connecting / multi-city itineraries",
    ],
}

# ---------------------------------------------------------------
# Like-for-like fare capture specification (Phase 3)
# ---------------------------------------------------------------
# CPI prices a FIXED item specification every period (e.g. one defined
# size/brand of a grocery item). The air-fare equivalent is captured
# here: every scrape records the SAME product — lowest published
# economy, non-refundable fare, booked exactly CAPTURE_LEAD_TIME_DAYS
# days before departure. If that exact quote is unavailable, the
# nearest available lead time within `lead_tolerance_days` is used
# (this is the "fallback specification", also common in CPI practice).
CAPTURE_SPEC = {
    "booking_class": "economy",
    "fare_type": "non_refundable",
    "lead_time_days": 15,
    "lead_tolerance_days": 3,
}

# ---------------------------------------------------------------
# Representative route basket weights (Phase 2)
# ---------------------------------------------------------------
# Each route's share of the aggregate index, proportional to its
# passenger-volume share. At full scale these come from DGCA / AAI
# traffic statistics; the values below are an ILLUSTRATIVE pilot-subset
# split for the 7 POC routes (they sum to 1.0) and are ordered to match
# the real top domestic sectors by traffic volume.
ROUTE_WEIGHTS = {
    ("DEL", "BOM"): 0.20,   # Delhi - Mumbai
    ("DEL", "BLR"): 0.18,   # Delhi - Bengaluru
    ("BOM", "BLR"): 0.15,   # Mumbai - Bengaluru
    ("DEL", "MAA"): 0.13,   # Delhi - Chennai
    ("BLR", "HYD"): 0.13,   # Bengaluru - Hyderabad
    ("BOM", "MAA"): 0.11,   # Mumbai - Chennai
    ("DEL", "CCU"): 0.10,   # Delhi - Kolkata
}

# ---------------------------------------------------------------
# Data-quality thresholds (Phase 4)
# ---------------------------------------------------------------
# Hard sanity band for any single domestic fare quote in INR.
OUTLIER_HARD_MIN = 1000.0
OUTLIER_HARD_MAX = 50000.0

# Statistical-outlier rule: a quote is flagged when it sits more than
# OUTLIER_IQR_FACTOR * IQR above the route+airline median (Tukey-style
# fence, one-sided high because low fares can be genuine promotions).
OUTLIER_IQR_FACTOR = 3.0

# Stale/cached-price rule: within a route+airline+source+lead-time
# chain of consecutive search dates, a quote whose price equals the
# previous day's price exactly (a cached page returns the identical
# stored value) is flagged as stale. Exact equality keeps false
# positives near zero while still catching cached/deduplicated pages.
STALE_PRICE_TOLERANCE = 0.0
