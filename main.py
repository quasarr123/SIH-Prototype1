"""
main.py
-------
Runs the full POC pipeline end-to-end, exactly as described in the
project brief:

    Flight fare data -> Data storage -> Data cleaning ->
    Baseline calculation -> Airfare Index -> (Dashboard visualization)

Run this once before launching the dashboard:

    python main.py

It will:
  1. Initialize the SQLite database (creates data/airfare.db).
  2. Generate ~30 days of mock fare-search data (if the DB is empty)
     and store it.
  3. Clean the stored data.
  4. Compute the baseline and the overall Airfare Index.
  5. Print a summary report to the console.
  6. Export a sample_fares.csv snapshot into data/, as the POC's
     required "sample dataset" deliverable.

The Streamlit dashboard (dashboard/app.py) re-runs steps 3-4 itself
on the data already stored in the DB, so it always reflects whatever
is currently in the database.
"""

import argparse
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from database import db  # noqa: E402
from data_collection.mock_data_generator import generate_mock_fares  # noqa: E402
from data_collection.collectors import get_ixigo_collector  # noqa: E402
from processing.cleaning import clean_fares, flagged_summary  # noqa: E402
from processing import index_calculator as idx  # noqa: E402
from config import SAMPLE_CSV_PATH, ROUTES, CAPTURE_SPEC  # noqa: E402


def collect_and_store(
    force_refresh: bool = False,
    live: bool = False,
    tolerant: bool = False,
) -> None:
    """Step 1-2: Flight fare data -> Data storage."""
    db.init_db()

    if force_refresh:
        db.clear_all_fares()

    if live:
        collect_live_ixigo(force_refresh=force_refresh, tolerant=tolerant)
        return

    if db.row_count() == 0:
        print("No data found in database. Generating mock fare data...")
        records = generate_mock_fares()
        inserted = db.insert_fares(records)
        print(f"Inserted {inserted} fare records into {db.DB_PATH}.")
        if records:
            spec = CAPTURE_SPEC
            db.log_scrape_run(
                scrape_id=records[0]["scrape_id"],
                source="|".join(sorted({r["source"] for r in records})),
                status="completed",
                records_expected=len(records),
                records_found=len(records),
                notes=(
                    f"mock generation; leads [7,14,{spec['lead_time_days']},30]; "
                    f"capture spec lead={spec['lead_time_days']}"
                ),
            )
            print("Scrape run logged in audit table (see scrape_runs).")
    else:
        print(f"Database already contains {db.row_count()} fare records — skipping generation.")
        print("(Run with --refresh to wipe and regenerate.)")


def collect_live_ixigo(
    force_refresh: bool = False,
    date: str | None = None,
    tolerant: bool = False,
) -> None:
    """
    Scrape live fares from Ixigo for all configured routes on the
    requested search/travel date, then store the results in the DB.

    NOTE: This opens a real Chrome window for each route/date combo.
    The scraper is a prototype for SIH 2026 (see collectors.py for the
    legal caveat).

    `tolerant=True` turns a completely empty scrape into a warning
    instead of a hard `sys.exit`, so a one-command launcher can still
    open the dashboard on whatever data already exists.
    """
    collector = get_ixigo_collector()
    if collector is None:
        print("Selenium/webdriver-manager not installed. Run: pip install -r requirements.txt")
        if tolerant:
            print("Continuing without live data (tolerant mode).")
            return
        sys.exit(1)

    from datetime import datetime, timedelta
    lead = CAPTURE_SPEC["lead_time_days"]  # default: the like-for-like 15-day booking lead
    travel_date = date or (datetime.now() + timedelta(days=lead)).strftime("%Y-%m-%d")

    if force_refresh:
        db.clear_all_fares()

    print(f"\n[LIVE] Scraping Ixigo for travel date {travel_date} ...")
    all_records = []
    for origin, destination in ROUTES:
        print(f"  -> {origin}-{destination}")
        records = collector.fetch(origin, destination, travel_date)
        all_records.extend(records)
        db.log_scrape_run(
            scrape_id=records[0]["scrape_id"] if records else "",
            source="Ixigo",
            origin=origin,
            destination=destination,
            travel_date=travel_date,
            status="completed" if records else "failed",
            records_found=len(records),
        )
        print(f"      found {len(records)} flights")

    if all_records:
        inserted = db.insert_fares(all_records)
        print(f"Inserted {inserted} live records from Ixigo into {db.DB_PATH}.")
    else:
        print("No live fares scraped. Check network / Ixigo selectors.")
        print("The Ixigo CSS selectors live in data_collection/ixigo_scraper.py.")
        if not tolerant:
            sys.exit(1)
        print("Tolerant mode: seeding mock fare data so the dashboard still runs "
              "on representative fares.")
        fallback_records = generate_mock_fares()
        inserted = db.insert_fares(fallback_records)
        if fallback_records:
            db.log_scrape_run(
                scrape_id=fallback_records[0]["scrape_id"],
                source="|".join(sorted({r["source"] for r in fallback_records})),
                status="completed",
                records_expected=len(fallback_records),
                records_found=len(fallback_records),
                notes="mock fallback (live Ixigo scrape empty)",
            )
        print(f"Inserted {inserted} mock fallback fare records into {db.DB_PATH}.")


def run_pipeline() -> None:
    raw_df = db.fetch_all_fares()
    print(f"\nLoaded {len(raw_df)} raw fare records from storage.")

    clean_df = clean_fares(raw_df)  # Step 3: Data cleaning (+ Phase-4 quality layer)
    print(f"{len(clean_df)} records remain after cleaning "
          f"({len(clean_df[clean_df['validation_status'] != 'flagged'])} passed quality checks).")

    # Phase 4: persist the per-row validation verdict back to the DB so
    # every stored fare is auditable (source + timestamp + passed?).
    updated = db.save_validation_results(clean_df)
    if updated:
        print(f"Audit trail updated: validation verdict saved for {updated} fare rows.")

    # Export the required "sample dataset" deliverable
    export_df = clean_df[
        clean_df["validation_status"] != "flagged"
    ].drop(columns=["validation_status"])
    export_df.to_csv(SAMPLE_CSV_PATH, index=False)
    print(f"Sample dataset exported to {SAMPLE_CSV_PATH}")

    flagged = flagged_summary(clean_df)
    if not flagged.empty:
        print("\n--- Flagged quotes by reason (Phase-4 quality layer) ---")
        print(flagged.to_string(index=False))

    # Step 4-5: Baseline calculation -> Airfare Index
    overall = idx.compute_overall_index(clean_df)
    route_df = idx.route_wise_index(clean_df)
    airline_df = idx.airline_wise_avg(clean_df)
    extremes = idx.cheapest_and_most_expensive_routes(route_df)

    print("\n================ AIRFARE INDEX SUMMARY ================")
    print(f"Method            : {overall['method']}")
    print(f"Baseline avg fare : Rs. {overall['baseline_avg_fare']:.2f} (weighted)")
    print(f"Current avg fare  : Rs. {overall['current_avg_fare']:.2f} (weighted)")
    print(f"Airfare Index     : {overall['airfare_index']}")
    print(f"Change vs baseline: {overall['pct_change']:+.2f} pts")
    print("\n--- Route-wise Index (weighted basket) ---")
    print(route_df[["route", "weight_pct", "baseline_avg_fare", "current_avg_fare",
                    "airfare_index", "index_pts"]].to_string(index=False))
    print("\n--- Airline-wise Current Avg Fare ---")
    print(airline_df.to_string(index=False))
    print("\n--- Cheapest / Most Expensive Route (current) ---")
    print(extremes)
    print("=========================================================\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Airfare Price Index POC — mock data or live Ixigo scrape."
    )
    parser.add_argument("--refresh", action="store_true",
                        help="Wipe the DB before inserting data.")
    parser.add_argument("--live", action="store_true",
                        help="Scrape live fares from Ixigo instead of using mock data.")
    parser.add_argument("--date", type=str, default=None,
                        help="Travel date (YYYY-MM-DD) to scrape in --live mode. "
                             "Defaults to 15 days out (the like-for-like capture-spec lead).")
    parser.add_argument("--tolerant", action="store_true",
                        help="In --live mode, continue (instead of exiting) when "
                             "the scrape finds no fares — used by the one-command "
                             "dashboard launcher so the app always opens.")
    args = parser.parse_args()

    collect_and_store(force_refresh=args.refresh, live=args.live, tolerant=args.tolerant)
    run_pipeline()
