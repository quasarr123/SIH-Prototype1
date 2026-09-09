"""
Automated validation test for APIx data pipeline.
Verifies database initialization, on-demand scraper, and Laspeyres index calculation.
"""
from database import init_db, get_routes, get_latest_quotes
from scraper import scrape_as_needed
from index_calc import calculate_apix, get_elasticity_curve

def run_tests():
    print("=== Step 1: Initializing Database ===")
    init_db()
    routes = get_routes()
    print(f"Loaded {len(routes)} representative DGCA routes.")
    assert len(routes) >= 5, "Expected at least 5 DGCA routes"

    print("\n=== Step 2: Testing On-Demand Scraper ===")
    quotes = scrape_as_needed("DEL-BOM", advance_days=7)
    print(f"Scraped {len(quotes)} quotes for DEL-BOM (T+7).")
    assert len(quotes) > 0, "Expected at least 1 scraped quote"
    sample = quotes[0]
    print(f"Sample Carrier: {sample['carrier']} | Flight: {sample['flight_number']}")
    print(f"Base Fare: Rs.{sample['base_fare']} | UDF: Rs.{sample['udf_charges']} | Taxes: Rs.{sample['taxes_fees']} | Total: Rs.{sample['total_fare']}")
    assert sample['total_fare'] == round(sample['base_fare'] + sample['udf_charges'] + sample['taxes_fees'], 2), "Unbundled fare must sum to total fare"

    print("\n=== Step 3: Testing Laspeyres Index Calculation ===")
    idx = calculate_apix()
    print(f"Computed Headline APIx: {idx['headline']}")
    print(f"T+1 Sub-index: {idx['apix_t1']} | T+30 Sub-index: {idx['apix_t30']}")
    assert idx['headline'] > 0, "Headline index must be positive"

    print("\n=== Step 4: Testing Price Elasticity Curve ===")
    curve = get_elasticity_curve()
    print(f"Elasticity points: {len(curve)}")
    assert len(curve) == 5, "Expected 5 advance windows in elasticity curve"

    print("\n[SUCCESS] All APIx pipeline tests passed successfully!")

if __name__ == "__main__":
    run_tests()
