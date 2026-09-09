"""
processing/cleaning.py
------------------------
Cleans raw fare data pulled from the database before it's used for
index calculation or dashboarding.

Real scraped data is messy (duplicate scrapes, missing fields,
currency symbols embedded in price strings, obvious outliers from a
mis-parsed page, etc.). This module centralizes those fixes so both
the index calculator and the dashboard work off clean data.
"""

import pandas as pd


REQUIRED_COLUMNS = [
    "source", "airline", "origin", "destination",
    "travel_date", "search_datetime", "fare_price",
]


def clean_fares(df: pd.DataFrame) -> pd.DataFrame:
    """
    Apply a standard cleaning pipeline to a raw fares DataFrame:
      1. Drop rows missing any required field.
      2. Coerce fare_price to numeric, drop rows that fail to parse.
      3. Drop non-positive or absurdly high fares (likely scrape errors).
      4. Drop exact duplicate quotes (same source/airline/route/
         travel_date/search_datetime/price scraped twice).
      5. Normalize text fields (trim whitespace, consistent casing
         for airport codes).
      6. Ensure date columns are proper datetimes.
    """
    if df.empty:
        return df

    cleaned = df.copy()

    # 1. Required fields present
    cleaned = cleaned.dropna(subset=REQUIRED_COLUMNS)

    # 2. Numeric fare price
    cleaned["fare_price"] = pd.to_numeric(cleaned["fare_price"], errors="coerce")
    cleaned = cleaned.dropna(subset=["fare_price"])

    # 3. Sane price bounds (domestic India fares in this POC: ~1,500 - 50,000 INR)
    cleaned = cleaned[(cleaned["fare_price"] >= 1000) & (cleaned["fare_price"] <= 50000)]

    # 4. De-duplicate
    dedup_cols = [
        "source", "airline", "origin", "destination",
        "travel_date", "search_datetime", "fare_price",
    ]
    cleaned = cleaned.drop_duplicates(subset=dedup_cols)

    # 5. Normalize text
    cleaned["origin"] = cleaned["origin"].str.strip().str.upper()
    cleaned["destination"] = cleaned["destination"].str.strip().str.upper()
    cleaned["airline"] = cleaned["airline"].str.strip()
    cleaned["source"] = cleaned["source"].str.strip()
    cleaned["route"] = cleaned["origin"] + "-" + cleaned["destination"]

    # 6. Dates
    cleaned["travel_date"] = pd.to_datetime(cleaned["travel_date"])
    cleaned["search_datetime"] = pd.to_datetime(cleaned["search_datetime"])
    cleaned["search_date"] = cleaned["search_datetime"].dt.date

    return cleaned.reset_index(drop=True)
