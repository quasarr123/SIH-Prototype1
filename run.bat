@echo off
rem One-click runner (Windows): creates .venv, installs deps, runs the pipeline.
rem Usage: run.bat            (mock data)
rem        run.bat --live     (live Ixigo scrape)
echo ================================
echo  SIH 2026 Airfare Index Prototype
echo ================================

IF NOT EXIST .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt --quiet

echo.
echo Starting pipeline...
python main.py %*

echo.
echo Done. Check "data\sample_fares.csv" and "data\airfare.db".
echo Dashboard: streamlit run dashboard/app.py
pause