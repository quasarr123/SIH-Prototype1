"""
dashboard/app.py
------------------
Streamlit dashboard for the Airfare Price Index POC.

Run with:
    streamlit run dashboard/app.py

Reads whatever is currently in the SQLite database (populate it
first by running `python main.py` from the project root), cleans it,
computes the Airfare Index, and renders the required dashboard views:
  1. Overall Airfare Index
  2. Current average airfare
  3. Percentage change from baseline
  4. Route-wise price comparison
  5. Price trend graph
  6. Airline-wise comparison
  7. Cheapest route
  8. Most expensive route
  9. Filters for route, airline, and travel date
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.append(str(Path(__file__).resolve().parent.parent))
import main as pipeline  # noqa: E402  (reuses orchestration; argparse only runs under __main__)
from database import db  # noqa: E402
from processing.cleaning import clean_fares, flagged_summary, coverage_report  # noqa: E402
from processing import index_calculator as idx  # noqa: E402
from config import (  # noqa: E402
    BASELINE_WINDOW_DAYS,
    CURRENT_WINDOW_DAYS,
    ROUTE_WEIGHTS,
    CAPTURE_SPEC,
    INDEX_BASE_VALUE,
    SCOPE,
)


st.set_page_config(
    page_title="India Airfare Price Index",
    page_icon="✈️",
    layout="wide",
)


# ---------------------------------------------------------------
# Data loading (cached so filter changes don't re-hit the DB)
# ---------------------------------------------------------------
@st.cache_data(ttl=60)
def load_clean_data() -> pd.DataFrame:
    db.init_db()
    if db.row_count() == 0:
        # One-command behaviour: if the DB is empty, seed it with mock
        # data so the app always opens with something to show.
        pipeline.collect_and_store(force_refresh=False, live=False, tolerant=True)
    raw = db.fetch_all_fares()
    return clean_fares(raw)


full_df = load_clean_data()

st.title("✈️ India Domestic Airfare Price Index")
st.caption(
    "CPI-compatible proof of concept (SIH 2026 / PS 26056) — a "
    "route-weighted, modified-Laspeyres index over a fixed basket of 7 "
    "domestic routes, built on like-for-like, quality-validated fares."
)


# ---------------------------------------------------------------
# Sidebar: collect-fresh control + filters
# ---------------------------------------------------------------
st.sidebar.header("Data")
collect_clicked = st.sidebar.button(
    "🔄 Scrape & update data now",
    help="Scrapes Ixigo for the latest fares, updates the database, then "
         "reloads the dashboard. Falls back to mock data if the scrape is empty.",
)
if collect_clicked:
    with st.spinner("Scraping Ixigo (one Chrome window per route)…"):
        pipeline.collect_and_store(
            force_refresh=True, live=True, tolerant=True
        )
    st.cache_data.clear()
    st.rerun()

if full_df.empty:
    st.warning(
        "No fare data found. Run `python main.py` from the project root first "
        "to generate and store the mock dataset, then reload this page."
    )
    st.stop()


# ---------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------
st.sidebar.header("Filters")

all_routes = sorted(full_df["route"].unique())
all_airlines = sorted(full_df["airline"].unique())
min_travel = full_df["travel_date"].min().date()
max_travel = full_df["travel_date"].max().date()

selected_routes = st.sidebar.multiselect(
    "Route", options=all_routes, default=all_routes
)
selected_airlines = st.sidebar.multiselect(
    "Airline", options=all_airlines, default=all_airlines
)
travel_date_range = st.sidebar.date_input(
    "Travel date range",
    value=(min_travel, max_travel),
    min_value=min_travel,
    max_value=max_travel,
)

st.sidebar.markdown("---")
st.sidebar.caption(
    f"Base period: earliest {BASELINE_WINDOW_DAYS} search days (index = "
    f"{INDEX_BASE_VALUE:g})\n\n"
    f"Current window: latest {CURRENT_WINDOW_DAYS} search days\n\n"
    f"Capture spec: {CAPTURE_SPEC['booking_class']}, {CAPTURE_SPEC['fare_type']}, "
    f"lead {CAPTURE_SPEC['lead_time_days']}d (±{CAPTURE_SPEC['lead_tolerance_days']}d)\n\n"
    f"Aggregation: route-weighted Laspeyres"
)

flagged_count = int((full_df["validation_status"] == "flagged").sum())
if flagged_count > 0:
    st.sidebar.warning(f"{flagged_count} quotes flagged by the quality layer "
                       f"(excluded from the index)")

# Apply filters
filtered_df = full_df[
    full_df["route"].isin(selected_routes) & full_df["airline"].isin(selected_airlines)
]
if isinstance(travel_date_range, tuple) and len(travel_date_range) == 2:
    start_d, end_d = travel_date_range
    filtered_df = filtered_df[
        (filtered_df["travel_date"].dt.date >= start_d)
        & (filtered_df["travel_date"].dt.date <= end_d)
    ]

if filtered_df.empty:
    st.warning("No data matches the current filters. Try widening your selection.")
    st.stop()


# ---------------------------------------------------------------
# Core calculations (on filtered data, so the index reacts to filters)
# ---------------------------------------------------------------
overall = idx.compute_overall_index(filtered_df)
route_df = idx.route_wise_index(filtered_df)
airline_df = idx.airline_wise_avg(filtered_df)
extremes = idx.cheapest_and_most_expensive_routes(route_df)
index_trend_df = idx.index_trend_over_time(filtered_df)


# ---------------------------------------------------------------
# 1-3. Headline metrics
# ---------------------------------------------------------------
m1, m2, m3, m4 = st.columns(4)

index_val = overall["airfare_index"]
delta_val = overall["pct_change"]

m1.metric(
    "Overall Airfare Index",
    f"{index_val:.2f}" if index_val is not None else "N/A",
    delta=f"{delta_val:+.2f} pts vs base" if delta_val is not None else None,
)
m2.metric(
    "Current Weighted Avg Fare",
    f"Rs. {overall['current_avg_fare']:,.0f}" if overall["current_avg_fare"] else "N/A",
)
m3.metric(
    "Base-period Avg Fare",
    f"Rs. {overall['baseline_avg_fare']:,.0f}" if overall["baseline_avg_fare"] else "N/A",
)
m4.metric(
    "Points vs Base",
    f"{delta_val:+.2f}" if delta_val is not None else "N/A",
)

if index_val is not None:
    if index_val > 100:
        st.info(
            f"📈 Fares are **{delta_val:+.2f} index points** above the base period "
            f"({INDEX_BASE_VALUE:g}) — aggregate fares have risen."
        )
    elif index_val < 100:
        st.success(
            f"📉 Fares are **{delta_val:+.2f} index points** below the base period "
            f"({INDEX_BASE_VALUE:g}) — aggregate fares have fallen."
        )
    else:
        st.info(f"Fares are exactly at the base-period level ({INDEX_BASE_VALUE:g}).")

st.markdown("---")


# ---------------------------------------------------------------
# 7-8. Cheapest / most expensive route callouts
# ---------------------------------------------------------------
c1, c2 = st.columns(2)
if extremes["cheapest"]:
    c1.success(
        f"🟢 **Cheapest route:** {extremes['cheapest']['route']} "
        f"— Rs. {extremes['cheapest']['avg_fare']:,.0f} avg"
    )
if extremes["most_expensive"]:
    c2.error(
        f"🔴 **Most expensive route:** {extremes['most_expensive']['route']} "
        f"— Rs. {extremes['most_expensive']['avg_fare']:,.0f} avg"
    )

st.markdown("---")


# ---------------------------------------------------------------
# 4. Route-wise comparison (weighted basket)
# ---------------------------------------------------------------
st.subheader("Route-wise Price Comparison (weighted basket)")
rc1, rc2 = st.columns([2, 3])

route_display = route_df.copy()
route_display["Weight"] = route_display["weight_pct"].astype(str) + "%"
route_display["Contribution (pts)"] = route_display["index_pts"]

with rc1:
    st.dataframe(
        route_display.rename(
            columns={
                "route": "Route",
                "baseline_avg_fare": "Baseline Avg (Rs.)",
                "current_avg_fare": "Current Avg (Rs.)",
                "airfare_index": "Index",
                "pct_change": "% Change",
            }
        )[
            ["Route", "Weight", "Baseline Avg (Rs.)", "Current Avg (Rs.)",
             "Index", "Contribution (pts)"]
        ],
        use_container_width=True,
        hide_index=True,
    )

with rc2:
    fig_route = px.bar(
        route_df,
        x="route",
        y=["baseline_avg_fare", "current_avg_fare"],
        barmode="group",
        labels={"route": "Route", "value": "Avg Fare (Rs.)", "variable": "Period"},
        title="Baseline vs Current Like-for-like Fare by Route",
    )
    st.plotly_chart(fig_route, use_container_width=True)

if "index_pts" in route_df.columns and not route_df.empty:
    st.caption(
        "Point contribution = route weight × price relative × 100. "
        "Each route's bars show how many points of the aggregate index it "
        "contributes (the stacked total equals the headline index)."
    )
    fig_contrib = px.bar(
        route_df,
        x="route",
        y="index_pts",
        color="route",
        labels={"route": "Route", "index_pts": "Index points contributed"},
        title="Route-weighted contribution to the aggregate index",
    )
    st.plotly_chart(fig_contrib, use_container_width=True)


# ---------------------------------------------------------------
# Methodology & quality (CPI-compatibility explainer)
# ---------------------------------------------------------------
with st.expander("See the CPI methodology behind this index"):
    st.markdown(
        f"""
This prototype implements the statistical rules MoSPI uses for CPI so the
result can slot into the *Transport & Communication* sub-group.

**1. Base period** — the index is pinned to the earliest
{BASELINE_WINDOW_DAYS} search days in the dataset ("base = {INDEX_BASE_VALUE:g}").
MoSPI's CPI uses 2012 = 100; because no granular air-fare capture predates this
system, a fresh, documented base period is defensible for a new sub-item.

**2. Scope** — {SCOPE['included']}. Excluded: {', '.join(SCOPE['excluded'])}.

**3. Route basket & weights** — 7 routes are the *pilot subset* of a nationally
representative basket chosen at scale from DGCA / AAI passenger-volume data.
Each route's weight is its passenger-volume share (summing to 1):

| Route | Weight |
|---|---|
""" +
        "".join(
            f"| {o}-{d} | {w*100:g}% |\n" for (o, d), w in ROUTE_WEIGHTS.items()
        )
        +
        f"""
**4. Like-for-like capture** — every quote prices the same item:
{CAPTURE_SPEC['booking_class'].title()}-class, {CAPTURE_SPEC['fare_type']}, booked
exactly {CAPTURE_SPEC['lead_time_days']} days before departure (fallback: nearest
lead within ±{CAPTURE_SPEC['lead_tolerance_days']} days). That is the air-fare
equivalent of CPI fixing one size/brand of a grocery item.

**5. Aggregation (modified Laspeyres)**

    I = Σ_r  w_r · (P_rt / P_r0) × 100

where w_r = route passenger share, P_rt = current like-for-like fare, P_r0 =
base-period like-for-like fare. This replaces the POC's former
`current avg / baseline avg × 100` with a CPI-grade weighted relative.

**6. Data quality & audit** — outliers and stale/cached quotes are detected and
flagged (never silently dropped), missing scrapes re-normalise weights over
available routes, and every stored fare is traceable to source + timestamp +
validation verdict (see `fares.validation_status`).
        """
    )

flagged_df = flagged_summary(full_df)
if not flagged_df.empty:
    st.warning(
        f"**{flagged_count} quotes flagged & excluded from the index** — "
        "these remain in the DB audit trail for transparency."
    )
    st.dataframe(flagged_df, hide_index=True, use_container_width=True)
    with st.expander("Per search-day route coverage (missing-scrape audit)"):
        cov = coverage_report(full_df)
        # only show rows with gaps or the latest days
        gap = cov[cov["coverage_pct"] < 100]
        if not gap.empty:
            st.dataframe(
                gap.sort_values("coverage_pct"),
                hide_index=True,
                use_container_width=True,
            )
        else:
            st.caption("All expected search-day × route quotes were captured.")

st.markdown("---")


# ---------------------------------------------------------------
# 5. Price trend graph
# ---------------------------------------------------------------
st.subheader("Price Trend Over Time")

trend_scope = st.radio(
    "Trend scope", ["All selected routes (overall)"] + selected_routes,
    horizontal=True,
)
route_for_trend = None if trend_scope.startswith("All") else trend_scope
trend_df = idx.price_trend_over_time(filtered_df, route=route_for_trend)

tc1, tc2 = st.columns(2)
with tc1:
    fig_trend = px.line(
        trend_df,
        x="search_date",
        y="avg_fare",
        markers=True,
        labels={"search_date": "Search Date", "avg_fare": "Avg Fare (Rs.)"},
        title=f"Average Fare Over Time — {trend_scope}",
    )
    st.plotly_chart(fig_trend, use_container_width=True)

with tc2:
    fig_index_trend = px.line(
        index_trend_df,
        x="search_date",
        y="airfare_index",
        markers=True,
        labels={"search_date": "Search Date", "airfare_index": "Airfare Index"},
        title=f"Weighted Laspeyres Airfare Index Over Time (base = {INDEX_BASE_VALUE:g})",
    )
    fig_index_trend.add_hline(y=INDEX_BASE_VALUE, line_dash="dash", line_color="gray")
    st.plotly_chart(fig_index_trend, use_container_width=True)


# ---------------------------------------------------------------
# 6. Airline-wise comparison
# ---------------------------------------------------------------
st.subheader("Airline-wise Comparison")
ac1, ac2 = st.columns([2, 3])

with ac1:
    st.dataframe(
        airline_df.rename(
            columns={
                "airline": "Airline",
                "current_avg_fare": "Current Avg Fare (Rs.)",
                "quote_count": "Quotes (current window)",
            }
        ),
        use_container_width=True,
        hide_index=True,
    )

with ac2:
    fig_airline = px.bar(
        airline_df,
        x="airline",
        y="current_avg_fare",
        color="airline",
        labels={"airline": "Airline", "current_avg_fare": "Current Avg Fare (Rs.)"},
        title="Current Average Fare by Airline",
    )
    st.plotly_chart(fig_airline, use_container_width=True)


st.markdown("---")
st.caption(
    "Data source: mock dataset generated for this POC (see README) — "
    "architecture supports plugging in a compliant live data source later."
)
