"""
processing/index_calculator.py
---------------------------------
All Airfare Index math lives here. Every function takes a CLEANED
fares DataFrame (see processing/cleaning.py, which adds "route" and
"search_date" columns) and returns either a DataFrame or a plain dict
of numbers — nothing here talks to the database or Streamlit, which
keeps it easy to unit-test and reuse.

Core formula (as specified):

    Airfare Index = (Current Average Fare / Baseline Average Fare) x 100

    * Baseline Average Fare = average fare during the EARLIEST
      `baseline_window_days` distinct search dates present in the data
      (i.e. the initial observation period).
    * Current Average Fare  = average fare during the LATEST
      `current_window_days` distinct search dates present in the data.

    100  -> fares unchanged from baseline
    >100 -> fares have risen
    <100 -> fares have fallen
"""

from typing import Optional

import pandas as pd

from config import BASELINE_WINDOW_DAYS, CURRENT_WINDOW_DAYS


def _baseline_window_dates(df: pd.DataFrame, window_days: int) -> pd.Series:
    all_dates = sorted(df["search_date"].unique())
    return pd.Series(all_dates[:window_days])


def _current_window_dates(df: pd.DataFrame, window_days: int) -> pd.Series:
    all_dates = sorted(df["search_date"].unique())
    return pd.Series(all_dates[-window_days:])


def _avg_fare_in_window(df: pd.DataFrame, dates: pd.Series) -> Optional[float]:
    subset = df[df["search_date"].isin(dates)]
    if subset.empty:
        return None
    return round(subset["fare_price"].mean(), 2)


def compute_overall_index(
    df: pd.DataFrame,
    baseline_window_days: int = BASELINE_WINDOW_DAYS,
    current_window_days: int = CURRENT_WINDOW_DAYS,
) -> dict:
    """
    Compute the single, headline Airfare Index across all routes/
    airlines/sources combined.

    Returns a dict:
        {
            "baseline_avg_fare": float,
            "current_avg_fare": float,
            "airfare_index": float,
            "pct_change": float,
            "baseline_dates": [date, ...],
            "current_dates": [date, ...],
        }
    """
    if df.empty:
        return {
            "baseline_avg_fare": None,
            "current_avg_fare": None,
            "airfare_index": None,
            "pct_change": None,
            "baseline_dates": [],
            "current_dates": [],
        }

    baseline_dates = _baseline_window_dates(df, baseline_window_days)
    current_dates = _current_window_dates(df, current_window_days)

    baseline_avg = _avg_fare_in_window(df, baseline_dates)
    current_avg = _avg_fare_in_window(df, current_dates)

    if not baseline_avg:
        index = None
        pct_change = None
    else:
        index = round((current_avg / baseline_avg) * 100, 2)
        pct_change = round(index - 100, 2)

    return {
        "baseline_avg_fare": baseline_avg,
        "current_avg_fare": current_avg,
        "airfare_index": index,
        "pct_change": pct_change,
        "baseline_dates": list(baseline_dates),
        "current_dates": list(current_dates),
    }


def route_wise_index(
    df: pd.DataFrame,
    baseline_window_days: int = BASELINE_WINDOW_DAYS,
    current_window_days: int = CURRENT_WINDOW_DAYS,
) -> pd.DataFrame:
    """
    Baseline avg, current avg, index, and pct change, one row per route.
    """
    if df.empty:
        return pd.DataFrame(
            columns=["route", "baseline_avg_fare", "current_avg_fare",
                     "airfare_index", "pct_change"]
        )

    baseline_dates = _baseline_window_dates(df, baseline_window_days)
    current_dates = _current_window_dates(df, current_window_days)

    rows = []
    for route, group in df.groupby("route"):
        baseline_avg = _avg_fare_in_window(group, baseline_dates)
        current_avg = _avg_fare_in_window(group, current_dates)
        if baseline_avg:
            index = round((current_avg / baseline_avg) * 100, 2)
            pct_change = round(index - 100, 2)
        else:
            index, pct_change = None, None
        rows.append(
            {
                "route": route,
                "baseline_avg_fare": baseline_avg,
                "current_avg_fare": current_avg,
                "airfare_index": index,
                "pct_change": pct_change,
            }
        )

    return pd.DataFrame(rows).sort_values("route").reset_index(drop=True)


def airline_wise_avg(
    df: pd.DataFrame,
    current_window_days: int = CURRENT_WINDOW_DAYS,
) -> pd.DataFrame:
    """
    Current average fare per airline, across all routes, plus how many
    quotes that's based on.
    """
    if df.empty:
        return pd.DataFrame(columns=["airline", "current_avg_fare", "quote_count"])

    current_dates = _current_window_dates(df, current_window_days)
    subset = df[df["search_date"].isin(current_dates)]

    grouped = (
        subset.groupby("airline")["fare_price"]
        .agg(current_avg_fare="mean", quote_count="count")
        .reset_index()
    )
    grouped["current_avg_fare"] = grouped["current_avg_fare"].round(2)
    return grouped.sort_values("current_avg_fare").reset_index(drop=True)


def cheapest_and_most_expensive_routes(route_df: pd.DataFrame) -> dict:
    """
    Given the output of route_wise_index(), return the cheapest and
    most expensive route by current average fare.
    """
    valid = route_df.dropna(subset=["current_avg_fare"])
    if valid.empty:
        return {"cheapest": None, "most_expensive": None}

    cheapest = valid.loc[valid["current_avg_fare"].idxmin()]
    priciest = valid.loc[valid["current_avg_fare"].idxmax()]
    return {
        "cheapest": {"route": cheapest["route"], "avg_fare": cheapest["current_avg_fare"]},
        "most_expensive": {"route": priciest["route"], "avg_fare": priciest["current_avg_fare"]},
    }


def price_trend_over_time(df: pd.DataFrame, route: Optional[str] = None) -> pd.DataFrame:
    """
    Daily average fare over time, optionally filtered to a single route
    (e.g. "DEL-BOM"). Used to plot the trend line / mini index-over-time
    chart on the dashboard.
    """
    if df.empty:
        return pd.DataFrame(columns=["search_date", "avg_fare"])

    subset = df if route is None else df[df["route"] == route]
    if subset.empty:
        return pd.DataFrame(columns=["search_date", "avg_fare"])

    trend = (
        subset.groupby("search_date")["fare_price"]
        .mean()
        .reset_index()
        .rename(columns={"fare_price": "avg_fare"})
        .sort_values("search_date")
    )
    trend["avg_fare"] = trend["avg_fare"].round(2)
    return trend


def index_trend_over_time(
    df: pd.DataFrame,
    baseline_window_days: int = BASELINE_WINDOW_DAYS,
) -> pd.DataFrame:
    """
    Airfare Index computed for EVERY search date (not just the latest
    window), so the dashboard can plot how the index itself has moved
    over the whole history — using the same fixed baseline throughout.
    """
    if df.empty:
        return pd.DataFrame(columns=["search_date", "avg_fare", "airfare_index"])

    baseline_dates = _baseline_window_dates(df, baseline_window_days)
    baseline_avg = _avg_fare_in_window(df, baseline_dates)
    if not baseline_avg:
        return pd.DataFrame(columns=["search_date", "avg_fare", "airfare_index"])

    daily = (
        df.groupby("search_date")["fare_price"]
        .mean()
        .reset_index()
        .rename(columns={"fare_price": "avg_fare"})
        .sort_values("search_date")
    )
    daily["avg_fare"] = daily["avg_fare"].round(2)
    daily["airfare_index"] = round((daily["avg_fare"] / baseline_avg) * 100, 2)
    return daily
