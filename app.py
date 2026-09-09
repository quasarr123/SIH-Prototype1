import os
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from database import init_db, get_routes, get_latest_quotes
from scraper import scrape_as_needed
from index_calc import calculate_apix, get_elasticity_curve, get_index_history, seed_demo_history_if_needed

app = FastAPI(
    title="Real-Time Airfare Price Index (APIx) - India",
    description="Student prototype for automated airfare scraping and Consumer Price Index (CPI) augmentation",
    version="1.0.0"
)

# Initialize database tables and seed routes
init_db()
seed_demo_history_if_needed()

# Mount frontend static directory
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

@app.get("/")
def serve_home():
    """Serves the main frontend dashboard."""
    index_path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "Frontend index.html not found yet. Please create frontend/index.html."}

@app.get("/api/routes")
def list_routes():
    """Returns the DGCA representative route basket and traffic weights."""
    return {"status": "success", "routes": get_routes()}

class ScrapeRequest(BaseModel):
    route_code: str = "DEL-BOM"
    advance_days: int = 7

@app.post("/api/scrape")
def trigger_scrape(req: ScrapeRequest):
    """
    On-Demand Scrape Endpoint:
    Scrapes or simulates new quotes strictly for the specified route and advance window.
    """
    quotes = scrape_as_needed(route_code=req.route_code, advance_days=req.advance_days)
    new_index = calculate_apix()
    return {
        "status": "success",
        "scraped_count": len(quotes),
        "route_code": req.route_code,
        "advance_days": req.advance_days,
        "quotes": quotes,
        "updated_index": new_index
    }

@app.get("/api/quotes")
def fetch_quotes(route_code: str = None, limit: int = 50):
    """Returns recently scraped airfare quotes with unbundled fare breakdown."""
    quotes = get_latest_quotes(limit=limit, route_code=route_code)
    return {"status": "success", "count": len(quotes), "quotes": quotes}

@app.get("/api/index")
def get_current_index():
    """Returns the current real-time Airfare Price Index (APIx) and sub-indices."""
    idx = calculate_apix()
    return {"status": "success", "index": idx}

@app.get("/api/history")
def get_history(limit: int = 20):
    """Returns historical APIx records for time-series charts."""
    history = get_index_history(limit=limit)
    return {"status": "success", "history": history}

@app.get("/api/elasticity")
def get_elasticity():
    """Returns booking lead-time price elasticity curve (T+1 to T+45)."""
    curve = get_elasticity_curve()
    return {"status": "success", "curve": curve}

if __name__ == "__main__":
    import uvicorn
    print("Starting APIx Backend Server on http://localhost:8000 ...")
    uvicorn.run("app:app", host="127.0.0.1", port=8000, reload=True)
