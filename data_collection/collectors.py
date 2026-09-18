"""
data_collection/collectors.py
------------------------------
Defines the COLLECTOR INTERFACE that every fare data source must
follow, plus stub implementations showing where real, compliant
scraping/API code would go.

IMPORTANT — why this POC does not scrape live sites:
Most Indian flight-booking websites (MakeMyTrip, Yatra, Cleartrip,
etc.) explicitly prohibit automated scraping in their Terms of
Service, and airline/OTA fare data is usually only available through
paid, licensed APIs (e.g. an airline's own partner API, or a GDS
such as Amadeus/Sabre). Scraping them without permission would
violate those terms, so this POC uses a mock data generator instead
(see mock_data_generator.py) that produces data in the EXACT same
shape a real collector would.

Because every collector below returns a list of dicts with the same
keys, the rest of the pipeline (storage, cleaning, index calculation,
dashboard) never needs to know whether the data came from a mock
generator, a licensed API, or a permitted scraper. To go live later,
you would:
    1. Get written permission / an API key from a data provider.
    2. Implement `fetch()` in a new class below using that provider's
       official API (preferred) or, if scraping is explicitly
       permitted (e.g. via robots.txt + ToS), Playwright/BeautifulSoup.
    3. Register the class in `ACTIVE_COLLECTORS`.
No other file needs to change.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Dict, Any


class BaseFareCollector(ABC):
    """
    Every real or mock data source implements this interface.
    `source_name` must match one of config.SOURCES.
    """

    source_name: str = "unknown"

    @abstractmethod
    def fetch(self, origin: str, destination: str, travel_date: str) -> List[Dict[str, Any]]:
        """
        Return a list of fare records (one per airline found) for the
        given route + travel date, each shaped as:

            {
                "source": self.source_name,
                "airline": str,
                "origin": origin,
                "destination": destination,
                "travel_date": travel_date,           # 'YYYY-MM-DD'
                "search_datetime": iso_timestamp_str,
                "fare_price": float,
                # Phase 3 — like-for-like capture specification
                "lead_time_days": int,                # (travel_date - search_date).days
                "booking_class": "economy",
                "fare_type": "non_refundable",
                # Phase 4 — audit trail
                "scrape_id": str,                     # this collection run's id
                "raw_fare_value": str,                # raw scraped text before parsing
                "source_url": str,                    # URL the fare was observed at
            }
        """
        raise NotImplementedError


class PlaywrightSiteACollector(BaseFareCollector):
    """
    STUB — real browser-automation collector for a compliant, permitted
    booking site, using Playwright (handles JS-rendered search results).

    Left unimplemented in the POC. Sketch of what production code
    would look like:

        from playwright.sync_api import sync_playwright

        def fetch(self, origin, destination, travel_date):
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(f"https://example-site/search?from={origin}"
                           f"&to={destination}&date={travel_date}")
                page.wait_for_selector(".fare-result-card")
                cards = page.query_selector_all(".fare-result-card")
                results = []
                for card in cards:
                    airline = card.query_selector(".airline-name").inner_text()
                    price = card.query_selector(".fare-price").inner_text()
                    results.append({
                        "source": self.source_name,
                        "airline": airline,
                        "origin": origin,
                        "destination": destination,
                        "travel_date": travel_date,
                        "search_datetime": datetime.now().isoformat(),
                        "fare_price": _parse_price(price),
                        # Phase 3/4: fill from CAPTURE_SPEC + page context
                        "lead_time_days": (parse_date(travel_date)
                                           - datetime.now().date()).days,
                        "booking_class": CAPTURE_SPEC["booking_class"],
                        "fare_type": CAPTURE_SPEC["fare_type"],
                        "scrape_id": str(uuid.uuid4()),
                        "raw_fare_value": price,
                        "source_url": page.url,
                    })
                browser.close()
                return results
    """

    source_name = "SkyFareHub"

    def fetch(self, origin: str, destination: str, travel_date: str) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "Live scraping is disabled in this POC. "
            "Use MockFareCollector via mock_data_generator.py instead, "
            "or implement this method against a licensed/permitted data source."
        )


class BeautifulSoupSiteBCollector(BaseFareCollector):
    """
    STUB — real static-HTML collector using requests + BeautifulSoup,
    for a site that renders fare results server-side.

    Sketch:

        import requests
        from bs4 import BeautifulSoup

        def fetch(self, origin, destination, travel_date):
            resp = requests.get(SEARCH_URL, params={...})
            soup = BeautifulSoup(resp.text, "html.parser")
            rows = soup.select(".result-row")
            ... same shape as above (incl. Phase-3/4 audit fields) ...
    """

    source_name = "TripEase"

    def fetch(self, origin: str, destination: str, travel_date: str) -> List[Dict[str, Any]]:
        raise NotImplementedError(
            "Live scraping is disabled in this POC. "
            "Use MockFareCollector via mock_data_generator.py instead, "
            "or implement this method against a licensed/permitted data source."
        )


# When real, compliant collectors are ready, list them here.
# The mock generator (mock_data_generator.py) is used instead for the POC.
ACTIVE_COLLECTORS = [
    PlaywrightSiteACollector(),
    BeautifulSoupSiteBCollector(),
]

# Lazy-loaded Ixigo collector (imported here to avoid hard dependency
# when running with mock data only).
def get_ixigo_collector():
    """Return an IxigoCollector instance, or None if selenium is missing."""
    try:
        from data_collection.ixigo_scraper import IxigoCollector
        return IxigoCollector()
    except ImportError:
        return None
