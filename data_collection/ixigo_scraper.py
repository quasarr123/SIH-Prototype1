"""
data_collection/ixigo_scraper.py
---------------------------------
Selenium-based fare collector for Ixigo (OTA).

Implements the BaseFareCollector interface so it plugs directly into
the existing pipeline — no changes needed downstream.

HOW IT WORKS
------------
Ixigo is a JavaScript SPA: the home page (https://www.ixigo.com/flights)
loads a search form, but the old-style deep links like
`/flights/DEL-BOM/{date}` now return 404.  The real results URL
(observed via a live search) is:

    /search/result/flight?from={ORIGIN}&to={DEST}&date={DDMMYYYY}&...
          &adults=1&children=0&infants=0&class=e&source=Search+Form

so this scraper navigates straight to that URL, waits for the flight
cards to render, then parses each card.

SELECTOR STABILITY
------------------
Where possible we anchor on `data-testid` attributes (e.g.
`data-testid="pricing"`) which Ixigo keeps stable, and fall back to
regex/text parsing of the card body when a class-based lookup misses
(class names like `pc_maxW115__wjiZg` include per-build hashes and can
change between deployments).

IMPORTANT — Legal note:
This collector is provided as a PROTOTYPE for SIH 2026.  Ixigo's
Terms of Service may restrict automated access.  For production use,
obtain permission or use an official API / licensed data feed.
"""

import re
import os
import time
import uuid
from datetime import datetime
from typing import List, Dict, Any

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
    NoSuchElementException,
)

from data_collection.collectors import BaseFareCollector

import sys
from pathlib import Path  # noqa: E402
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))
from config import CAPTURE_SPEC  # noqa: E402

# ---------------------------------------------------------------------------
# Ixigo-specific configuration
# ---------------------------------------------------------------------------
# Results URL — this is the canonical search-results URL the SPA uses
# after submitting the form (verified via live search, 2026-09).
IXIGO_URL_TEMPLATE = (
    "https://www.ixigo.com/search/result/flight?"
    "from={origin}&to={destination}&date={ddmmyyyy}"
    "&adults=1&children=0&infants=0&class=e&source=Search+Form"
)

# CSS/attribute selectors — anchored on stable test-ids where possible.
IXIGO_SELECTORS = {
    # One flight row. Screenshots showed cards matching shadow-card + cursor-pointer.
    "flight_card":      "div[class*='shadow-card'][class*='cursor-pointer']",
    "price":            "h6[data-testid='pricing']",
    "airline":          ".airlineTruncate",
    "times":            ".//div[contains(@class,'timeTile')]//h6",
    "airport_codes":    "div[class*='timeTile'] p[class*='text-critical-500']",
}

HEADLESS = os.environ.get("IXIGO_HEADLESS", "0") == "1"  # set IXIGO_HEADLESS=1 for unattended runs
PAGE_LOAD_TIMEOUT = 45
RESULT_WAIT_TIMEOUT = 25   # how long to wait for the first card
EXTRA_RENDER_WAIT = 5       # settle time after the first card appears
SCROLL_ROUNDS = 4           # lazy-load deeper results
SCROLL_WAIT = 1.2
MAX_FLIGHTS_PER_ROUTE = 25  # cap rows scraped per route+date


def _parse_price(raw: str) -> float | None:
    """Extract a numeric INR price from strings like '₹6,442' or 'Rs. 4523'."""
    digits = re.sub(r"[^\d.]", "", raw or "")
    if not digits:
        return None
    try:
        return float(digits)
    except ValueError:
        return None


def _to_ddmmyyyy(date_str: str) -> str:
    """Convert 'YYYY-MM-DD' -> 'DDMMYYYY' (Ixigo results URL format)."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d%m%Y")
    except ValueError:
        return date_str.replace("-", "")


class IxigoCollector(BaseFareCollector):
    """
    Selenium scraper for Ixigo flight search results.

    Usage:
        collector = IxigoCollector()
        fares = collector.fetch("DEL", "BOM", "2026-09-16")

    A fresh headless/headed Chrome driver is created per fetch().
    """

    source_name = "Ixigo"

    # ------------------------------------------------------------------
    # Public interface (matches BaseFareCollector)
    # ------------------------------------------------------------------
    def fetch(
        self, origin: str, destination: str, travel_date: str
    ) -> List[Dict[str, Any]]:
        """Scrape Ixigo for one route + travel date; return fare dicts."""
        driver = self._make_driver()
        try:
            return self._scrape_route(driver, origin, destination, travel_date)
        finally:
            try:
                driver.quit()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Driver setup
    # ------------------------------------------------------------------
    @staticmethod
    def _make_driver() -> webdriver.Chrome:
        options = webdriver.ChromeOptions()
        if HEADLESS:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0 Safari/537.36"
        )
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            service = Service(ChromeDriverManager().install())
        except Exception:
            # Fallback: assume chromedriver is already on PATH.
            service = Service()
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)
        return driver

    # ------------------------------------------------------------------
    # Scraping
    # ------------------------------------------------------------------
    def _scrape_route(
        self,
        driver: webdriver.Chrome,
        origin: str,
        destination: str,
        travel_date: str,
    ) -> List[Dict[str, Any]]:
        url = IXIGO_URL_TEMPLATE.format(
            origin=origin,
            destination=destination,
            ddmmyyyy=_to_ddmmyyyy(travel_date),
        )
        scrape_id = str(uuid.uuid4())

        try:
            driver.get(url)
        except WebDriverException as exc:
            print(f"  [IxigoCollector] Could not load {origin}-{destination}: {exc}")
            return []

        # Wait for the first flight card to render
        try:
            WebDriverWait(driver, RESULT_WAIT_TIMEOUT).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, IXIGO_SELECTORS["flight_card"])
                )
            )
        except TimeoutException:
            print(
                f"  [IxigoCollector] No flight cards on {origin}-{destination}"
                f"/{travel_date} — selectors may need updating."
            )
            return []
        except WebDriverException as exc:
            print(f"  [IxigoCollector] Driver error on {travel_date}: {exc}")
            return []

        time.sleep(EXTRA_RENDER_WAIT)

        # Lazy load more results by scrolling, collecting unique cards.
        # Note: Selenium returns a fresh proxy per query, so dedupe on the
        # parsed content (airline + dep + arr + price), not element identity.
        seen: set = set()
        flights: List[Dict[str, Any]] = []

        for _ in range(SCROLL_ROUNDS + 1):
            for card in self._current_cards(driver):
                parsed = self._parse_card(
                    card, origin, destination, travel_date,
                    scrape_id=scrape_id, source_url=url,
                )
                if not parsed or parsed["fare_price"] is None:
                    continue
                key = (
                    parsed["airline"],
                    parsed["departure_time"],
                    parsed["arrival_time"],
                    parsed["fare_price"],
                )
                if key in seen:
                    continue
                seen.add(key)
                flights.append(parsed)
                if len(flights) >= MAX_FLIGHTS_PER_ROUTE:
                    return flights
            try:
                driver.execute_script("window.scrollBy(0, 1500);")
                time.sleep(SCROLL_WAIT)
            except WebDriverException:
                break

        return flights

    def _current_cards(self, driver: webdriver.Chrome) -> list:
        try:
            return driver.find_elements(
                By.CSS_SELECTOR, IXIGO_SELECTORS["flight_card"]
            )
        except WebDriverException:
            return []

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------
    def _parse_card(self, card, origin, destination, travel_date,
                    scrape_id: str = "", source_url: str = ""):
        try:
            text = card.text  # entire card text
        except WebDriverException:
            return None
        if not text:
            return None

        price = self._css_text(card, IXIGO_SELECTORS["price"])
        price_num = _parse_price(price)
        if price_num is None:
            # Fallback: first ₹/Rs token in the card body
            m = re.search(r"[₹Rs\.\s]*([\d,]+)", text)
            price_num = _parse_price(m.group(1)) if m else None
        if price_num is None:
            return None

        airline = self._css_text(card, IXIGO_SELECTORS["airline"]).strip()
        if not airline:
            m = re.search(r"^\s*([A-Za-z\- ]+?)\s*$", text.splitlines()[0] if text.splitlines() else "")
            airline = m.group(1).strip() if m else "Unknown"

        dep = ""
        arr = ""
        try:
            time_els = card.find_elements(By.XPATH, IXIGO_SELECTORS["times"])
            if len(time_els) > 0:
                dep = self._elm_text(time_els[0])
            if len(time_els) > 1:
                arr = self._elm_text(time_els[1])
        except WebDriverException:
            pass

        codes = card.find_elements(By.CSS_SELECTOR, IXIGO_SELECTORS["airport_codes"])
        dep_code = self._elm_text(codes[0]) if len(codes) > 0 else ""
        arr_code = self._elm_text(codes[1]) if len(codes) > 1 else ""
        if not dep_code:
            dep_code = dep.split()[-1] if dep else ""
        if not arr_code:
            arr_code = arr.split()[-1] if arr else ""

        duration = ""
        m = re.search(r"(\d{1,2}h\s?\d{0,2}m?)", text)
        if m:
            duration = m.group(1)

        try:
            lead_time_days = (
                datetime.strptime(travel_date, "%Y-%m-%d").date() - datetime.now().date()
            ).days
        except ValueError:
            lead_time_days = None

        return {
            "source": self.source_name,
            "airline": airline,
            "origin": origin,
            "destination": destination,
            "travel_date": travel_date,
            "search_datetime": datetime.now().isoformat(timespec="seconds"),
            "fare_price": price_num,
            "lead_time_days": lead_time_days,
            "booking_class": CAPTURE_SPEC["booking_class"],
            "fare_type": CAPTURE_SPEC["fare_type"],
            "scrape_id": scrape_id,
            "raw_fare_value": text,
            "source_url": source_url,
            "departure_time": dep,
            "arrival_time": arr,
            "departure_code": dep_code,
            "arrival_code": arr_code,
            "duration": duration,
        }

    # ------------------------------------------------------------------
    # Small DOM helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _css_text(parent, selector: str) -> str:
        try:
            el = parent.find_element(By.CSS_SELECTOR, selector)
            return el.text.strip()
        except (NoSuchElementException, WebDriverException):
            return ""

    @staticmethod
    def _elm_text(el) -> str:
        try:
            return el.text.strip()
        except WebDriverException:
            return ""