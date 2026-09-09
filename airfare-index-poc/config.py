"""
config.py
---------
Central place for constants shared across the whole POC:
routes tracked, airlines tracked, mock data sources, and
baseline-window settings for the Airfare Index.

Keeping these in one file means the scraping module, the
index calculator, and the dashboard all agree on the same
definitions.
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
SOURCES = ["SkyFareHub", "TripEase"]

# ---------------------------------------------------------------
# Airfare Index settings
# ---------------------------------------------------------------
# Number of most-recent distinct search dates that make up the
# "baseline" observation period against which the index is measured.
BASELINE_WINDOW_DAYS = 7

# Number of most-recent distinct search dates considered "current".
CURRENT_WINDOW_DAYS = 3
