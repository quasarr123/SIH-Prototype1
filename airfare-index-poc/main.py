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

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent))

from database import db  # noqa: E402
from data_collection.mock_data_generator import generate_mock_fares  # noqa: E402
from processing.cleaning import clean_fares  # noqa: E402
from processing import index_calculator as idx  # noqa: E402
from config import SAMPLE_CSV_PATH  # noqa: E402


def collect_and_store(force_refresh: bool = False) -> None:
    """Step 1-2: Flight fare data -> Data storage."""
    db.init_db()

    if force_refresh:
        db.clear_all_fares()

    if db.row_count() == 0:
        print("No data found in database. Generating mock fare data...")
        records = generate_mock_fares()
        inserted = db.insert_fares(records)
        print(f"Inserted {inserted} fare records into {db.DB_PATH}.")
    else:
        print(f"Database already contains {db.row_count()} fare records — skipping generation.")
        print("(Run with --refresh to wipe and regenerate.)")


def run_pipeline() -> None:
    raw_df = db.fetch_all_fares()
    print(f"\nLoaded {len(raw_df)} raw fare records from storage.")

    clean_df = clean_fares(raw_df)  # Step 3: Data cleaning
    print(f"{len(clean_df)} records remain after cleaning.")

    # Export the required "sample dataset" deliverable
    clean_df.to_csv(SAMPLE_CSV_PATH, index=False)
    print(f"Sample dataset exported to {SAMPLE_CSV_PATH}")

    # Step 4-5: Baseline calculation -> Airfare Index
    overall = idx.compute_overall_index(clean_df)
    route_df = idx.route_wise_index(clean_df)
    airline_df = idx.airline_wise_avg(clean_df)
    extremes = idx.cheapest_and_most_expensive_routes(route_df)

    print("\n================ AIRFARE INDEX SUMMARY ================")
    print(f"Baseline avg fare : Rs. {overall['baseline_avg_fare']:.2f}")
    print(f"Current avg fare  : Rs. {overall['current_avg_fare']:.2f}")
    print(f"Airfare Index     : {overall['airfare_index']}")
    print(f"Change vs baseline: {overall['pct_change']:+.2f}%")
    print("\n--- Route-wise Index ---")
    print(route_df.to_string(index=False))
    print("\n--- Airline-wise Current Avg Fare ---")
    print(airline_df.to_string(index=False))
    print("\n--- Cheapest / Most Expensive Route (current) ---")
    print(extremes)
    print("=========================================================\n")


if __name__ == "__main__":
    force_refresh = "--refresh" in sys.argv
    collect_and_store(force_refresh=force_refresh)
    run_pipeline()
