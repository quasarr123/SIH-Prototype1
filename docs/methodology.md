# Methodology — Real-time Airfare Price Index (CPI Augmentation)

**Project:** SIH 2026 · Problem Statement 26056 · MoSPI, Data Informatics &
Innovation Division
**Deliverable this document supports:** a CPI-compatible air-travel price
*relative* — not a CPI calculation — built with the same statistical rules
MoSPI applies to every other CPI item, so it can feed the *Transport &
Communication* sub-group.

The POC implements everything below for a **7-route pilot subset**. Each
section states the production rule and, where the POC uses a stand-in, the
exact production source.

---

## 1. Base period & scope

**Base period.** The index is referenced to a fixed, documented base period,
mirroring the CPI convention of a reference period (MoSPI CPI base:
**2012 = 100**). Because no granular air-fare capture for India predates this
system, the POC defines a *new* defensible base: the **earliest 7 distinct
search dates** in the dataset (`BASELINE_WINDOW_DAYS`). The index equals
**100.0** in the base period, and every later period is measured as a price
relative against it:

```text
I_base = 100.0   (all P_rt and P_r0 coincide in the base period by construction)
```

The base window is a fixed, pinned reference; it does not roll forward, which
keeps the resulting series comparable over time in the same way CPI
sub-indices are.

**Scope.** The item being priced is:

> *Domestic, economy-class air travel within India, one-way, non-refundable
> fare per airline as displayed on OTA/airline portals at a standard booking
> lead time.*

Explicitly **excluded**: international travel, air cargo, business/first
class, charter and private aviation, and connecting / multi-city
itineraries. The index therefore measures only the CPI-relevant "domestic
economy air passenger transport" item.

---

## 2. Representative route basket & weighting

**Basket selection (production).** The basket is the **top N domestic city
pairs by passenger traffic**, taken from **DGCA / AAI monthly traffic
statistics** (directed origin–destination sectors by passengers carried). N
is chosen so the basket covers a substantial pre-set share of total domestic
passenger-kilometres or passengers (e.g. top 20–25 sectors covering >50% of
domestic traffic). This is the same logic used to fix a CPI basket: it is
representative, sizes the market, and is re-verified periodically.

**Pilot subset (in the POC).** The 7 implemented routes
(DEL–BOM, DEL–BLR, BOM–BLR, DEL–MAA, BLR–HYD, BOM–MAA, DEL–CCU) are the
demo slice of that basket, deliberately chosen as the country's busiest
domestic sectors.

**Weights.** Each route contributes to the aggregate in proportion to its
share of domestic passenger volumes, `w_r` with `Σ w_r = 1`. In production
`w_r = passengers_r / Σ_passengers_basket`. The POC ships illustrative
pilot-subset shares (see `config.ROUTE_WEIGHTS`), ordered to match real
traffic ranks.

**Basket review.** The basket and its weights are reviewed on the same
cadence as CPI basket revision (typically every few years or on significant
market change), so long-run drift in travel patterns does not silently
distort the index.

---

## 3. Like-for-like fare capture specification

CPI prices a *fixed item specification* every period (a defined size/brand of
a grocery item). The air-fare equivalent is a strict capture rule so that two
data points are always "the same product":

> **Capture rule (one quote per airline per route per search):** the lowest
> published **economy**, **non-refundable** fare for a booking made exactly
> **15 days before departure** (`CAPTURE_SPEC.lead_time_days`).

**Fallback rule.** If the exact 15-day quote is unavailable, the nearest
available lead time within **±3 days** (`lead_tolerance_days`) is captured and
its actual lead recorded (`capture_lead_time_days`); the row is still
like-for-like because the reference lead stays fixed.

**Why this rule:** lead time, cabin class and refundability dominate Indian
domestic fare variability; holding them fixed removes the largest
period-over-period noise sources and isolates the price movement the CPI
item is meant to capture. Every stored row is tagged with `lead_time_days`,
`booking_class` and `fare_type` so the rule is enforced in `processing/`
rather than left to the collector's whim.

---

## 4. Data-quality layer & audit trail

Feeding an official statistic requires "correct", not "mostly right", data.
The pipeline handles the four failure modes:

| Failure | Rule | Implementation |
|---|---|---|
| **Outlier** (mis-parsed price) | Hard band `[1,000 – 50,000] INR`; plus Tukey fence: flag quotes more than `3 × IQR` *above* the route+airline median (one-sided high — cheap promo fares are legitimate) | `cleaning.detect_outliers` |
| **Stale / cached page** | A quote that exactly repeats the previous day's price for the same route+airline+source+lead is flagged `cached_price_repeat` (a cached page returns the identical stored value) | `cleaning.flag_stale_prices` |
| **Missing scrape** | Routes without a valid quote simply drop out; remaining route weights re-normalise to sum 1, so a failed scrape cannot bias the aggregate. Coverage is audited per (search day, route) | `cleaning.coverage_report`; `index_calculator._weights_for` |
| **Audit trail** | Every fare row carries `scrape_id`, `raw_fare_value`, `source_url`, `search_datetime`, and `validation_status`/`flag_reason` (persisted post-cleaning). Collection runs are recorded in `scrape_runs` | `database/schema.sql`, `db.save_validation_results`, `db.log_scrape_run` |

Flagged rows are **never silently destroyed** — they are excluded from the
index but remain in the DB for audit, so judges/MoSPI can inspect what was
thrown away and why.

---

## 5. CPI-compatible aggregation (modified Laspeyres)

MoSPI aggregates CPI sub-indices with a **modified Laspeyres index**: fixed
base-period weights applied to current-period price relatives. The airfare
index implements the same structure:

```text
I_t = ( Σ_r  w_r · ( P_rt / P_r0 ) ) × 100
```

where, for route `r` in the basket at period `t`:

| Term | Meaning |
|---|---|
| `P_r0` | base-period like-for-like fare for route `r` |
| `P_rt` | current-period like-for-like fare for route `r` |
| `P_rt / P_r0` | route price relative (like-for-like, quality-validated) |
| `w_r` | base-period passenger-volume weight, `Σ w_r = 1` |

Route averages are computed from quotes passing the Phase-4 checks *and*
matching the Phase-3 capture spec, then grouped to a single route reference
fare. `index_calculator.route_price_relatives` exposes the full route-level
table (baseline fare, current fare, relative, weight, index-point contribution)
so the aggregation is fully transparent.

**Before / after (for the pitch):**

```text
Before:  Index = (current avg of ALL quotes) / (baseline avg of ALL quotes) × 100
         — one equal-weighted ratio mixing cabin classes, lead times and junk.

After:   Index = Σ w_r · (P_rt / P_r0) × 100
         — a passenger-volume-weighted, fixed-basket, like-for-like,
           quality-validated Laspeyres-style aggregate.
```

A daily version of the same formula (`index_trend_over_time`) is computed
against the single fixed base period so the dashboard can plot how the index
itself has moved over the full history.

---

## Where each rule lives in the code

| Rule | Location |
|---|---|
| Base period & scope constants | `config.py` (`BASELINE_WINDOW_DAYS`, `SCOPE`, `INDEX_BASE_VALUE`) |
| Route basket & weights | `config.py` (`ROUTES`, `ROUTE_WEIGHTS`) |
| Capture specification | `config.py` (`CAPTURE_SPEC`) + `processing/cleaning.apply_capture_spec` |
| Quality rules | `processing/cleaning.py` (`detect_outliers`, `flag_stale_prices`, `mark_validation`) |
| Audit schema | `database/schema.sql` (+ lightweight migration in `database/db.py`) |
| Laspeyres aggregation | `processing/index_calculator.py` |
| Reporting / dashboard | `main.py`, `dashboard/app.py` |