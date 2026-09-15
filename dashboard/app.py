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
from database import db  # noqa: E402
from processing.cleaning import clean_fares  # noqa: E402
from processing import index_calculator as idx  # noqa: E402
from config import BASELINE_WINDOW_DAYS, CURRENT_WINDOW_DAYS  # noqa: E402


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
    raw = db.fetch_all_fares()
    return clean_fares(raw)


full_df = load_clean_data()

st.title("✈️ India Domestic Airfare Price Index")
st.caption(
    "Proof of Concept — tracks fares across 7 popular domestic routes from "
    "2 data sources, and calculates an Airfare Index relative to a baseline period."
)

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
    f"Baseline window: earliest {BASELINE_WINDOW_DAYS} search days\n\n"
    f"Current window: latest {CURRENT_WINDOW_DAYS} search days"
)

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
    delta=f"{delta_val:+.2f} pts vs 100" if delta_val is not None else None,
)
m2.metric(
    "Current Avg Fare",
    f"Rs. {overall['current_avg_fare']:,.0f}" if overall["current_avg_fare"] else "N/A",
)
m3.metric(
    "Baseline Avg Fare",
    f"Rs. {overall['baseline_avg_fare']:,.0f}" if overall["baseline_avg_fare"] else "N/A",
)
m4.metric(
    "% Change from Baseline",
    f"{delta_val:+.2f}%" if delta_val is not None else "N/A",
)

if index_val is not None:
    if index_val > 100:
        st.info(f"📈 Fares are **{delta_val:+.2f}%** above the baseline — prices have risen.")
    elif index_val < 100:
        st.success(f"📉 Fares are **{delta_val:+.2f}%** below the baseline — prices have fallen.")
    else:
        st.info("Fares are exactly at the baseline level.")

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
# 4. Route-wise comparison
# ---------------------------------------------------------------
st.subheader("Route-wise Fare Comparison")
rc1, rc2 = st.columns([2, 3])

with rc1:
    st.dataframe(
        route_df.rename(
            columns={
                "route": "Route",
                "baseline_avg_fare": "Baseline Avg (Rs.)",
                "current_avg_fare": "Current Avg (Rs.)",
                "airfare_index": "Index",
                "pct_change": "% Change",
            }
        ),
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
        title="Baseline vs Current Average Fare by Route",
    )
    st.plotly_chart(fig_route, use_container_width=True)


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
        title="Airfare Index Over Time (baseline = 100)",
    )
    fig_index_trend.add_hline(y=100, line_dash="dash", line_color="gray")
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
