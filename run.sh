#!/usr/bin/env bash
# One-click runner: creates .venv, installs deps, runs the pipeline.
# Usage: ./run.sh              (mock data)
#        ./run.sh --live       (live Ixigo scrape)
set -e
echo "================================"
echo " SIH 2026 Airfare Index Prototype"
echo "================================"

if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

echo "Installing dependencies..."
pip install -r requirements.txt --quiet

echo
echo "Starting pipeline..."
python main.py "$@"

echo
echo "Done. Check 'data/sample_fares.csv' and 'data/airfare.db'."
echo "Dashboard: streamlit run dashboard/app.py"