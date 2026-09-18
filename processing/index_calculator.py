"""
processing/index_calculator.py
---------------------------------
All Airfare Index math lives here. Every function takes a CLEANED
fares DataFrame (see processing/cleaning.py, which adds "route",
"search_date", "lead_time_days" and the Phase-4 validation columns) and
returns either a DataFrame or a plain dict of numbers — nothing here
talks to the database or Streamlit, which keeps it easy to unit-test
and reuse.

CPI-compatible aggregation (Phase 5)
------------------------------------
MoSPI aggregates CPI sub-indices with a **modified Laspeyres index**:
fixed base-period weights applied to current-period price relatives.

    I_t = ( Σ_r  w_r · ( P_rt / P_r0 ) ) × 100

    I_t          — aggregate airfare index in period t (base = 100)
    r            — route in the representative basket
    w_r          — base-period weight of route r (passenger-volume share,
                   Σ w_r = 1)  [Phase 2]
    P_rt         — current-period like-for-like reference fare for route r
    P_r0         — base-period like-for-like reference fare for route r

Price relatives P_rt / P_r0 are computed from like-for-like quotes only
(Phase 3 capture spec via processing.cleaning.apply_capture_spec) and
from rows that PASSED the Phase-4 quality checks, so the comparison is
always "the same item" and never polluted by scrape errors.

Before/after for the pitch:
    Before:  Index = (current avg fare of ALL quotes) / (baseline avg
             fare of ALL quotes) × 100  — a single equal-weighted ratio
             that mixes cabin classes, lead times and scraped junk.
    After:   Index = Σ w_r · (P_rt / P_r0) × 100  — a passenger-volume
             weighted Laspeyres-style aggregate over fixed-basket routes,
             using like-for-like, quality-validated reference fares.
"""

from typing import Optional

import pandas as pd

from config import (
    BASELINE_WINDOW_DAYS,
    CURRENT_WINDOW_DAYS,
    INDEX_BASE_VALUE,
    ROUTE_WEIGHTS,
)
from processing import cleaning

_INDEX_METHOD = "modified Laspeyres (route passenger-volume weights)"


def route_weight_map() -> dict:
    """Map 'DEL-BOM' style route strings to passenger-volume weights."""
    return {f"{o}-{d}": w for (o, d), w in ROUTE_WEIGHTS.items()}


def _weights_for(routes, route_weights: dict | None = None) -> pd.Series:
    """
    Return base-period weights aligned to `routes`, re-normalised to sum
    to 1 over whatever routes are actually present. Missing-data strategy:
    routes with no quotes simply drop out and the remaining weights are
    re-scaled, so the aggregate is not biased by a failed scrape run.
    """
    base = route_weights if route_weights is not None else route_weight_map()
    routes = list(routes)
    w = pd.Series({r: float(base.get(r, 0.0)) for r in routes})
    total = w.sum()
    if total <= 0:
        w = pd.Series(1.0, index=pd.Index(routes))
    else:
        w = w / total
    return w


def _baseline_window_dates(df: pd.DataFrame, window_days: int) -> pd.Series:
    all_dates = sorted(df["search_date"].unique())
    return pd.Series(all_dates[:window_days])


def _current_window_dates(df: pd.DataFrame, window_days: int) -> pd.Series:
    all_dates = sorted(df["search_date"].unique())
    return pd.Series(all_dates[-window_days:])


def _reference_frame(df: pd.DataFrame) -> pd.DataFrame:
    """
    Reduce a cleaned frame to the quotes that are (a) like-for-like
    (Phase-3 capture spec) and (b) quality-validated (Phase-4: flagged
    outliers / stale repeats excluded). This is the only data that ever
    reaches the aggregation below.
    """
    if df.empty:
        return df
    d = df.copy()
    if "validation_status" in d.columns:
        d = d[d["validation_status"] != "flagged"]
    return cleaning.apply_capture_spec(d)


def _route_mean(ref: pd.DataFrame, dates) -> pd.Series:
    subset = ref[ref["search_date"].isin(dates)]
    if subset.empty:
        return pd.Series(dtype=float)
    return subset.groupby("route", sort=True)["fare_price"].mean()


def route_price_relatives(
    df: pd.DataFrame,
    baseline_window_days: int = BASELINE_WINDOW_DAYS,
    current_window_days: int = CURRENT_WINDOW_DAYS,
    route_weights: dict | None = None,
) -> pd.DataFrame:
    """
    Build the route-level price relatives that feed the Laspeyres
    aggregate:

        baseline_fare  = P_r0  (mean like-for-like fare, base window)
        current_fare   = P_rt  (mean like-for-like fare, current window)
        price_relative = P_rt / P_r0
        weight         = w_r   (re-normalised passenger-volume share)
        index_pts      = w_r · (P_rt / P_r0) · 100   (contribution to I_t)
        chg_pts        = w_r · (P_rt / P_r0 − 1) · 100 (contribution to Δ)
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "route", "baseline_fare", "current_fare", "price_relative",
                "weight", "index_pts", "chg_pts",
            ]
        )

    ref = _reference_frame(df)
    baseline_dates = _baseline_window_dates(df, baseline_window_days)
    current_dates = _current_window_dates(df, current_window_days)

    base_ser = _route_mean(ref, baseline_dates)
    cur_ser = _route_mean(ref, current_dates)

    routes = sorted(set(base_ser.index) & set(cur_ser.index))
    if not routes:
        return pd.DataFrame(
            columns=[
                "route", "baseline_fare", "current_fare", "price_relative",
                "weight", "index_pts", "chg_pts",
            ]
        )

    weights = _weights_for(routes, route_weights)
    rel = pd.DataFrame(
        {
            "route": routes,
            "baseline_fare": base_ser.reindex(routes).round(2).values,
            "current_fare": cur_ser.reindex(routes).round(2).values,
        }
    )
    rel["price_relative"] = (rel["current_fare"] / rel["baseline_fare"]).round(4)
    rel["weight"] = weights.reindex(routes).round(4).values
    rel["index_pts"] = (rel["weight"] * rel["price_relative"] * INDEX_BASE_VALUE).round(2)
    rel["chg_pts"] = (rel["weight"] * (rel["price_relative"] - 1) * INDEX_BASE_VALUE).round(2)
    return rel


def _laspeyres_aggregate(rel: pd.DataFrame) -> float:
    """I_t = Σ w_r · (P_rt / P_r0) × 100 over the available basket."""
    return round((rel["price_relative"] * rel["weight"]).sum() * INDEX_BASE_VALUE, 2)


def compute_overall_index(
    df: pd.DataFrame,
    baseline_window_days: int = BASELINE_WINDOW_DAYS,
    current_window_days: int = CURRENT_WINDOW_DAYS,
    route_weights: dict | None = None,
) -> dict:
    """
    Compute the single, headline, CPI-compatible Airfare Index.

    Returns a dict:
        {
            "baseline_avg_fare": float,   # Σ w_r · P_r0 (weighted)
            "current_avg_fare": float,    # Σ w_r · P_rt (weighted)
            "airfare_index": float,       # weighted Laspeyres index (base 100)
            "pct_change": float,          # index − 100
            "baseline_dates": [...],
            "current_dates": [...],
            "method": str,
            "route_relatives": DataFrame,
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
            "method": _INDEX_METHOD,
            "route_relatives": pd.DataFrame(),
        }

    rel = route_price_relatives(
        df, baseline_window_days, current_window_days, route_weights
    )
    if rel.empty:
        return {
            "baseline_avg_fare": None,
            "current_avg_fare": None,
            "airfare_index": None,
            "pct_change": None,
            "baseline_dates": list(_baseline_window_dates(df, baseline_window_days)),
            "current_dates": list(_current_window_dates(df, current_window_days)),
            "method": _INDEX_METHOD,
            "route_relatives": rel,
        }

    index = _laspeyres_aggregate(rel)
    baseline_avg = round((rel["baseline_fare"] * rel["weight"]).sum(), 2)
    current_avg = round((rel["current_fare"] * rel["weight"]).sum(), 2)
    pct_change = round(index - INDEX_BASE_VALUE, 2)

    return {
        "baseline_avg_fare": baseline_avg,
        "current_avg_fare": current_avg,
        "airfare_index": index,
        "pct_change": pct_change,
        "baseline_dates": list(_baseline_window_dates(df, baseline_window_days)),
        "current_dates": list(_current_window_dates(df, current_window_days)),
        "method": _INDEX_METHOD,
        "route_relatives": rel,
    }


def route_wise_index(
    df: pd.DataFrame,
    baseline_window_days: int = BASELINE_WINDOW_DAYS,
    current_window_days: int = CURRENT_WINDOW_DAYS,
    route_weights: dict | None = None,
) -> pd.DataFrame:
    """
    Per-route basis of the aggregate: baseline/current like-for-like
    fare, the route price relative, the route's simple index
    (= relative × 100), its weight, and its point contribution.
    """
    if df.empty:
        return pd.DataFrame(
            columns=[
                "route", "baseline_avg_fare", "current_avg_fare",
                "price_relative", "airfare_index", "pct_change",
                "weight", "weight_pct", "index_pts", "chg_pts",
            ]
        )

    rel = route_price_relatives(
        df, baseline_window_days, current_window_days, route_weights
    )
    if rel.empty:
        return pd.DataFrame(
            columns=[
                "route", "baseline_avg_fare", "current_avg_fare",
                "price_relative", "airfare_index", "pct_change",
                "weight", "weight_pct", "index_pts", "chg_pts",
            ]
        )

    out = rel.rename(
        columns={
            "baseline_fare": "baseline_avg_fare",
            "current_fare": "current_avg_fare",
        }
    )
    out["price_relative"] = out["price_relative"].round(4)
    out["airfare_index"] = (out["price_relative"] * INDEX_BASE_VALUE).round(2)
    out["pct_change"] = (out["airfare_index"] - INDEX_BASE_VALUE).round(2)
    out["weight_pct"] = (out["weight"] * 100).round(2)
    return out.reset_index(drop=True)


def airline_wise_avg(
    df: pd.DataFrame,
    current_window_days: int = CURRENT_WINDOW_DAYS,
) -> pd.DataFrame:
    """
    Current average like-for-like fare per airline across all routes,
    plus how many valid quotes that's based on.
    """
    if df.empty:
        return pd.DataFrame(columns=["airline", "current_avg_fare", "quote_count"])

    ref = _reference_frame(df)
    current_dates = _current_window_dates(df, current_window_days)
    subset = ref[ref["search_date"].isin(current_dates)]

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
    Daily average like-for-like fare over time, optionally filtered to a
    single route (e.g. "DEL-BOM"). Used to plot the trend line chart.
    """
    if df.empty:
        return pd.DataFrame(columns=["search_date", "avg_fare"])

    ref = _reference_frame(df)
    subset = ref if route is None else ref[ref["route"] == route]
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
    route_weights: dict | None = None,
) -> pd.DataFrame:
    """
    Weighted Laspeyres Airfare Index computed for EVERY search date
    (not just the latest window) against the same fixed base period, so
    the dashboard can plot how the index itself moved over the history.
    Routes missing on a given day drop out and the weights re-normalise.
    """
    if df.empty:
        return pd.DataFrame(columns=["search_date", "avg_fare", "airfare_index"])

    ref = _reference_frame(df)
    baseline_dates = _baseline_window_dates(df, baseline_window_days)
    base_ser = _route_mean(ref, baseline_dates)
    if base_ser.empty:
        return pd.DataFrame(columns=["search_date", "avg_fare", "airfare_index"])

    rows = []
    for day in sorted(ref["search_date"].unique()):
        day_subset = ref[ref["search_date"] == day]
        cur_ser = day_subset.groupby("route", sort=True)["fare_price"].mean()
        common = sorted(set(base_ser.index) & set(cur_ser.index))
        if not common:
            continue
        weights = _weights_for(common, route_weights)
        relative = cur_ser.reindex(common) / base_ser.reindex(common)
        index_val = (relative * weights.reindex(common)).sum() * INDEX_BASE_VALUE
        avg_fare = (cur_ser.reindex(common) * weights.reindex(common)).sum()
        rows.append(
            {
                "search_date": day,
                "avg_fare": round(avg_fare, 2),
                "airfare_index": round(index_val, 2),
                "routes_covered": len(common),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["search_date", "avg_fare", "airfare_index", "routes_covered"])
    return pd.DataFrame(rows)