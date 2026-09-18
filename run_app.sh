#!/usr/bin/env bash
# One-command launcher: scrape the latest fares -> update the database ->
# then open the Streamlit dashboard. Everything in one command.
#
# Usage:  ./run_app.sh            (scrape Ixigo live, then dashboard)
#         USE_MOCK=1 ./run_app.sh (regenerate mock data instead of scraping)
set -e
echo "========================================="
echo " Airfare Index — Collect + Dashboard"
echo "========================================="

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi
source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt --quiet

echo
if [ "$USE_MOCK" = "1" ]; then
    echo "Generating fresh mock dataset..."
    python main.py --refresh
else
    echo "Scraping the latest fares from Ixigo and updating the database..."
    echo "(Fallback: if the scrape finds nothing, it will keep existing data and still open the dashboard.)"
    # --refresh: rebuild from scratch so the base/current windows are fresh;
    # --tolerant: never let a failed scrape stop the dashboard from opening.
    python main.py --live --refresh --tolerant
fi

echo
echo "Launching dashboard at http://localhost:8501 ..."
streamlit run dashboard/app.py