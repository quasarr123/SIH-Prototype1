"""
processing/cleaning.py
------------------------
Cleans raw fare data pulled from the database before it's used for
index calculation or dashboarding.

Real scraped data is messy (duplicate scrapes, missing fields,
currency symbols embedded in price strings, obvious outliers from a
mis-parsed page, stale/cached pages returning yesterday's fare, etc.).
This module centralizes those fixes so both the index calculator and
the dashboard work off clean data.

CPI-compatibility (SIH 2026 / PS 26056):
  * `clean_fares` is the standard structural pipeline (extended, not
    replaced) and now also runs the Phase-4 data-quality layer:
    outlier detection, stale/cached-price detection, and a per-row
    validation verdict so every stored fare is traceable to "did it
    pass quality checks" before it feeds the index.
  * `apply_capture_spec` enforces the Phase-3 like-for-like capture
    rule: of the quotes available for a (search date, route, airline,
    source), the one whose booking lead time is closest to the
    reference lead (CAPTURE_SPEC["lead_time_days"]) is selected, and
    only if it falls within the tolerance window. This guarantees the
    index always prices "the same item" period over period.
  * `coverage_report` turns missing scrapes into a measurable audit
    table (expected vs captured quotes per search day + route).
"""

import numpy as np
import pandas as pd

from config import (
    CAPTURE_SPEC,
    OUTLIER_HARD_MIN,
    OUTLIER_HARD_MAX,
    OUTLIER_IQR_FACTOR,
    STALE_PRICE_TOLERANCE,
)

REQUIRED_COLUMNS = [
    "source", "airline", "origin", "destination",
    "travel_date", "search_datetime", "fare_price",
]


# ---------------------------------------------------------------------------
# Phase 4 — data-quality layer
# ---------------------------------------------------------------------------
def detect_outliers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flag obviously wrong prices rather than silently destroying them:
      1. Hard band: any quote below OUTLIER_HARD_MIN or above
         OUTLIER_HARD_MAX (impossible for domestic economy India fares).
      2. Statistical fence: a quote more than OUTLIER_IQR_FACTOR * IQR
         ABOVE the route+airline median (Tukey-style, one-sided high —
         genuine promotions can be cheap, but scrape errors are almost
         always absurdly HIGH).

    Adds columns: outlier_flag (bool), outlier_reason (str).
    """
    df = df.copy()
    df["outlier_flag"] = False
    df["outlier_reason"] = ""

    if df.empty:
        return df

    hard = (df["fare_price"] < OUTLIER_HARD_MIN) | (df["fare_price"] > OUTLIER_HARD_MAX)
    df.loc[hard, "outlier_flag"] = True
    df.loc[hard, "outlier_reason"] = "outside_expected_band"

    in_band = df[~hard].copy()
    if not in_band.empty:
        grp = in_band.groupby(["route", "airline"], sort=False)["fare_price"]
        q1 = grp.transform(lambda s: s.quantile(0.25))
        q3 = grp.transform(lambda s: s.quantile(0.75))
        iqr = q3 - q1
        upper = q3 + OUTLIER_IQR_FACTOR * iqr
        stat = in_band["fare_price"] > upper
        idx = in_band.index[stat]
        if len(idx):
            df.loc[idx, "outlier_flag"] = True
            df.loc[idx, "outlier_reason"] = "statistical_high_outlier"

    return df


def flag_stale_prices(df: pd.DataFrame) -> pd.DataFrame:
    """
    Stale / cached-price detection: within each
    (route, airline, source, lead_time) chain ordered by search date, a
    quote that repeats the previous day's price (within
    STALE_PRICE_TOLERANCE) is flagged as a likely cached page.

    Adds columns: stale_flag (bool), stale_reason (str).
    """
    df = df.copy()
    df["stale_flag"] = False
    df["stale_reason"] = ""

    if df.empty or "search_date" not in df.columns:
        return df

    sort = df.sort_values(
        ["route", "airline", "source", "lead_time_days", "search_date"]
    )
    keys = ["route", "airline", "source", "lead_time_days"]
    grp = sort.groupby(keys, sort=False)
    prev_price = grp["fare_price"].shift(1)
    prev_date = grp["search_date"].shift(1)

    delta_days = (sort["search_date"] - prev_date).dt.days
    same_price = (
        (sort["fare_price"] - prev_price).abs() / sort["fare_price"]
    ) <= STALE_PRICE_TOLERANCE
    consecutive = (prev_date.notna()) & (delta_days == 1)

    stale = consecutive & same_price
    idx = sort.index[stale.fillna(False)]
    if len(idx):
        df.loc[idx, "stale_flag"] = True
        df.loc[idx, "stale_reason"] = "cached_price_repeat"

    return df


def mark_validation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Combine the quality flags into a single per-row verdict:
        validation_status = 'flagged' | 'passed'
        flag_reason       = semicolon-joined reasons ('' when passed)
    """
    df = df.copy()

    reason_parts = []
    for flag_col, reason_col in (
        ("outlier_flag", "outlier_reason"),
        ("stale_flag", "stale_reason"),
    ):
        part = df[reason_col].where(df.get(flag_col, pd.Series(index=df.index)).fillna(False), "")
        reason_parts.append(part)

    combined = reason_parts[0].combine(
        reason_parts[1], lambda a, b: ";".join(x for x in (a, b) if x)
    )
    df["flag_reason"] = combined
    df["validation_status"] = np.where(combined != "", "flagged", "passed")
    return df


def run_quality_validation(df: pd.DataFrame) -> pd.DataFrame:
    """Outlier -> stale -> verdict, in one shot."""
    df = detect_outliers(df)
    df = flag_stale_prices(df)
    return mark_validation(df)


def flagged_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Count of flagged rows per reason (for console/dashboard reporting)."""
    if df.empty or "validation_status" not in df.columns:
        return pd.DataFrame(columns=["reason", "count"])
    rows = df.loc[df["validation_status"] == "flagged", "flag_reason"]
    counts: dict = {}
    for reason in rows:
        for r in str(reason).split(";"):
            if r:
                counts[r] = counts.get(r, 0) + 1
    return (
        pd.DataFrame(counts.items(), columns=["reason", "count"])
        .sort_values("count", ascending=False)
        .reset_index(drop=True)
    )


# ---------------------------------------------------------------------------
# Phase 3 — like-for-like capture specification
# ---------------------------------------------------------------------------
def apply_capture_spec(
    df: pd.DataFrame,
    lead_time_days: int | None = None,
    tolerance_days: int | None = None,
) -> pd.DataFrame:
    """
    Enforce the fixed capture specification (Phase 3): for each
    (search_date, route, airline, source) keep the single quote whose
    booking lead time is closest to the reference lead time, provided it
    is within `tolerance_days`. This is the like-for-like filter that
    makes period-over-period price relatives statistically valid.

    Idempotent: calling it on an already-reduced frame returns the same
    rows (each group contains one row -> it is the closest & within
    tolerance by construction after the first pass).
    """
    ref_lead = lead_time_days if lead_time_days is not None else CAPTURE_SPEC["lead_time_days"]
    tol = tolerance_days if tolerance_days is not None else CAPTURE_SPEC["lead_tolerance_days"]

    if df.empty or "lead_time_days" not in df.columns:
        return df

    df = df.copy()
    grp = df.groupby(["search_date", "route", "airline", "source"], sort=False)["lead_time_days"]
    best = grp.apply(lambda s: int(abs(s - ref_lead).idxmin())).rename("_best_idx")
    out = df.loc[list(best.values)]
    out["capture_lead_time_days"] = out["lead_time_days"]
    in_tol = (out["capture_lead_time_days"] - ref_lead).abs() <= tol
    return out.loc[in_tol].reset_index(drop=True)


def coverage_report(df: pd.DataFrame) -> pd.DataFrame:
    """
    Missing-data audit (Phase 4): for each (search_date, route), compare
    the number of quotes EXPECTED (all airline x source combos seen
    anywhere in the data) with the number CAPTURED after the like-for-like
    capture-spec filter and after excluding flagged rows. Reports per-row
    counts and a coverage %. The index handles gaps by re-normalising
    route weights over whatever WAS captured (see index_calculator).
    """
    if df.empty:
        return pd.DataFrame(
            columns=["search_date", "route", "expected_quotes", "captured_quotes", "coverage_pct"]
        )

    expected = (
        df[["search_date", "route", "airline", "source"]]
        .drop_duplicates()
        .groupby(["search_date", "route"], sort=False)
        .size()
        .rename("expected_quotes")
    )

    passed = df[df["validation_status"] == "passed"] if "validation_status" in df.columns else df
    ref = apply_capture_spec(passed)
    actual = (
        ref.groupby(["search_date", "route"], sort=False)
        .size()
        .rename("captured_quotes")
    )

    report = expected.to_frame().join(actual, how="outer").fillna(0)
    report["captured_quotes"] = report["captured_quotes"].astype(int)
    report["coverage_pct"] = (
        report["captured_quotes"] / report["expected_quotes"] * 100
    ).round(1)
    return report.reset_index()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def clean_fares(df: pd.DataFrame) -> pd.DataFrame:
    """
    Structural cleaning + Phase-4 quality validation (extended pipeline):

      1. Drop rows missing any required field.
      2. Coerce fare_price to numeric, drop rows that fail to parse.
      3. Drop structurally impossible fares (below OUTLIER_HARD_MIN).
         Above-band fares are FLAGGED (not dropped) so the audit trail
         stays complete — see run_quality_validation.
      4. Drop exact duplicate quotes.
      5. Normalize text fields (trim whitespace, consistent casing
         for airport codes) and derive `route`.
      6. Coerce dates to datetimes and derive `search_date`,
         `lead_time_days` (Phase 3).
      7. Run outlier / stale detection and set `validation_status` /
         `flag_reason` (Phase 4).
    """
    if df.empty:
        return df

    cleaned = df.copy()

    # 1. Required fields present
    cleaned = cleaned.dropna(subset=REQUIRED_COLUMNS)

    # 2. Numeric fare price
    cleaned["fare_price"] = pd.to_numeric(cleaned["fare_price"], errors="coerce")
    cleaned = cleaned.dropna(subset=["fare_price"])

    # 3. Structurally impossible fares (below the plausible floor) are dropped;
    #    above-band values are kept for the audit trail and flagged later.
    cleaned = cleaned[cleaned["fare_price"] > OUTLIER_HARD_MIN]

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

    # 6. Dates + Phase-3 capture fields
    cleaned["travel_date"] = pd.to_datetime(cleaned["travel_date"])
    cleaned["search_datetime"] = pd.to_datetime(cleaned["search_datetime"])
    cleaned["search_date"] = cleaned["search_datetime"].dt.normalize()
    cleaned["lead_time_days"] = (
        cleaned["travel_date"] - cleaned["search_date"]
    ).dt.days
    cleaned["booking_class"] = cleaned["booking_class"].fillna(CAPTURE_SPEC["booking_class"])
    cleaned["fare_type"] = cleaned["fare_type"].fillna(CAPTURE_SPEC["fare_type"])

    # 7. Quality validation (Phase 4)
    cleaned = run_quality_validation(cleaned)

    return cleaned.reset_index(drop=True)