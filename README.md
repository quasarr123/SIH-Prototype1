# Real-Time Airfare Price Index (APIx) for India ✈️

> **Smart India Hackathon Prototype**  
> *Development of a Real-time Airfare Price Index for India through Automated Web Scraping of Airline and Online Travel Aggregator Portals for Augmentation of the Consumer Price Index (CPI).*

---

## 📌 Project Overview
The **Airfare Price Index (APIx)** is a student-friendly end-to-end prototype designed to:
1. **Targeted / On-Demand Scraping**: Extracts airfare quotes across Indian carriers (IndiGo, Air India, Akasa Air, SpiceJet) across representative advance-purchase windows ($T+1, T+7, T+15, T+30, T+45$).
2. **Fare Unbundling**: Decomposes ticket prices into Base Fare, User Development Fee (UDF), and Taxes/GST/Convenience charges.
3. **DGCA Traffic-Weighted Laspeyres Index**: Computes headline APIx using official Directorate General of Civil Aviation (DGCA) passenger traffic weights for India's top domestic corridors (DEL-BOM, DEL-BLR, BOM-BLR, etc.).
4. **CPI Augmentation for NSO & RBI**: Provides high-frequency price signals to eliminate the 45-day reporting lag in official CPI (Transport sub-group).
5. **Interactive Web Dashboard**: Built with HTML, CSS, JavaScript (Chart.js), and FastAPI.

---

## 📁 Simple Project Structure
```
SIH-Prototype/
├── schema.sql           # Complete MariaDB / MySQL table definitions & DGCA seed data
├── .env                 # Database credentials & configuration
├── requirements.txt     # Python dependencies (FastAPI, uvicorn, pymysql, requests, etc.)
├── database.py          # MariaDB connector with automatic SQLite fallback (apix.db)
├── scraper.py           # On-demand scraper & realistic dynamic pricing engine
├── index_calc.py        # Laspeyres index calculator with advance window sub-indices
├── app.py               # FastAPI backend server
└── frontend/
    ├── index.html       # Clean web dashboard (controls, KPI cards, fare table)
    ├── style.css        # Responsive modern dark styling
    └── app.js           # Vanilla JS for API calls & Chart.js live charts
```

---

## 🗄️ Database Setup (MariaDB)

1. **Option A: Run with MariaDB (Recommended)**
   - Open your MariaDB / MySQL prompt or HeidiSQL / DBeaver:
     ```sql
     SOURCE schema.sql;
     ```
   - Update your credentials in `.env`:
     ```env
     DB_HOST=localhost
     DB_PORT=3306
     DB_USER=root
     DB_PASSWORD=your_mariadb_password
     DB_NAME=apix_db
     ```

2. **Option B: Automatic SQLite Fallback**
   - If MariaDB is not yet configured or password is unset, the Python backend **automatically falls back to a local `apix.db` SQLite database** with identical schemas and seeded DGCA routes. Zero manual setup required to start testing immediately!

---

## 🚀 How to Run

1. **Install Dependencies**:
   ```bash
   uv pip install -r requirements.txt
   # OR
   pip install -r requirements.txt
   ```

2. **Start the Backend & Web Dashboard**:
   ```bash
   python app.py
   ```
   *The server starts on:* **`http://localhost:8000`**

3. **Interact with the Platform**:
   - Open `http://localhost:8000` in your browser.
   - Choose a DGCA route (e.g. `DEL ➔ BOM`) and advance window (e.g. `T+7`).
   - Click **"Scrape Fares As Needed"**.
   - Watch the KPI cards, Trend Line, Elasticity Curve, and Fare Table update instantly!
