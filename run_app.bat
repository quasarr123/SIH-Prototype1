@echo off
rem One-command launcher (Windows): scrape the latest fares -> update the
rem database -> then open the Streamlit dashboard.
rem Usage:  run_app.bat            (scrape Ixigo live, then dashboard)
rem         set USE_MOCK=1 && run_app.bat  (regenerate mock data instead)
echo =========================================
echo  Airfare Index - Collect + Dashboard
echo =========================================

IF NOT EXIST .venv (
    echo Creating virtual environment...
    python -m venv .venv
)
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install -r requirements.txt --quiet

echo.
if "%USE_MOCK%"=="1" (
    echo Generating fresh mock dataset...
    python main.py --refresh
) else (
    echo Scraping the latest fares from Ixigo and updating the database...
    python main.py --live --refresh --tolerant
)

echo.
echo Launching dashboard at http://localhost:8501 ...
streamlit run dashboard\app.py