import datetime
import random
from database import get_routes, get_latest_quotes, save_index_record, get_index_history

# Advance Purchase Window Weights in Consumer Behavior
# Based on typical domestic Indian airline booking patterns
ADVANCE_WEIGHTS = {
    1: 0.15,   # T+1: Emergency / Last-minute (15%)
    7: 0.25,   # T+7: Short-term / Business (25%)
    15: 0.30,  # T+15: Standard advance (30%)
    30: 0.20,  # T+30: Vacationers / Planners (20%)
    45: 0.10   # T+45: Early-bird (10%)
}

def calculate_apix():
    """
    Computes the Real-Time Airfare Price Index (APIx) using the Laspeyres
    weighted index formula:

        APIx = ( Sum( P_it * W_i ) / Sum( P_i0 * W_i ) ) * 100

    where:
      - P_it = Current average fare for route i
      - P_i0 = Baseline reference fare for route i
      - W_i  = DGCA passenger traffic volume weight
    """
    routes = get_routes()
    if not routes:
        return {"headline": 100.0, "sub_indices": {}, "status": "no_routes"}

    quotes = get_latest_quotes(limit=200)

    # If no quotes exist yet, calculate a baseline
    if not quotes:
        return {
            "headline": 100.0,
            "apix_t1": 165.0,
            "apix_t7": 125.0,
            "apix_t15": 105.0,
            "apix_t30": 100.0,
            "apix_t45": 92.0,
            "sample_size": 0,
            "calc_date": str(datetime.date.today())
        }

    # Group quotes by advance_days and route
    # structure: prices_by_window[advance_days][route_code] = [fare1, fare2...]
    prices_by_window = {1: {}, 7: {}, 15: {}, 30: {}, 45: {}}
    all_route_prices = {}

    for q in quotes:
        adv = q["advance_days"]
        rcode = q["route_code"]
        fare = float(q["total_fare"])

        if adv in prices_by_window:
            prices_by_window[adv].setdefault(rcode, []).append(fare)
        all_route_prices.setdefault(rcode, []).append(fare)

    # Base basket denominator: Sum(P_i0 * W_i)
    denom = sum(float(r["base_price_p0"]) * float(r["dgca_weight"]) for r in routes)
    if denom == 0:
        denom = 1.0

    # Calculate sub-indices for each advance window (T+1, T+7, etc.)
    sub_indices = {}
    for adv, route_dict in prices_by_window.items():
        numerator = 0.0
        for r in routes:
            rcode = r["route_code"]
            w = float(r["dgca_weight"])
            p0 = float(r["base_price_p0"])
            # If quotes exist for this route and window, use average; else use p0 * advance factor
            if rcode in route_dict and route_dict[rcode]:
                p_it = sum(route_dict[rcode]) / len(route_dict[rcode])
            else:
                adv_mult = {1: 1.65, 7: 1.25, 15: 1.05, 30: 1.00, 45: 0.92}.get(adv, 1.0)
                p_it = p0 * adv_mult
            numerator += p_it * w
        sub_indices[adv] = round((numerator / denom) * 100.0, 2)

    # Calculate Composite Headline APIx
    headline_apix = sum(sub_indices[adv] * ADVANCE_WEIGHTS[adv] for adv in ADVANCE_WEIGHTS)
    headline_apix = round(headline_apix, 2)

    today = str(datetime.date.today())
    sample_size = len(quotes)

    # Save to history table
    save_index_record(
        calc_date=today,
        headline=headline_apix,
        t1=sub_indices.get(1, 100.0),
        t7=sub_indices.get(7, 100.0),
        t15=sub_indices.get(15, 100.0),
        t30=sub_indices.get(30, 100.0),
        t45=sub_indices.get(45, 100.0),
        sample_size=sample_size
    )

    return {
        "headline": headline_apix,
        "apix_t1": sub_indices.get(1, 100.0),
        "apix_t7": sub_indices.get(7, 100.0),
        "apix_t15": sub_indices.get(15, 100.0),
        "apix_t30": sub_indices.get(30, 100.0),
        "apix_t45": sub_indices.get(45, 100.0),
        "sample_size": sample_size,
        "calc_date": today
    }

def get_elasticity_curve():
    """Returns price elasticity values across advance windows for charting."""
    idx = calculate_apix()
    return [
        {"window": "T+1 (1 Day)", "days": 1, "index": idx["apix_t1"]},
        {"window": "T+7 (1 Week)", "days": 7, "index": idx["apix_t7"]},
        {"window": "T+15 (15 Days)", "days": 15, "index": idx["apix_t15"]},
        {"window": "T+30 (1 Month)", "days": 30, "index": idx["apix_t30"]},
        {"window": "T+45 (45 Days)", "days": 45, "index": idx["apix_t45"]}
    ]

def seed_demo_history_if_needed():
    """Populates 14 days of realistic historical index readings for smooth charting."""
    history = get_index_history(limit=5)
    if len(history) < 5:
        today = datetime.date.today()
        base_val = 104.2
        for d in range(14, 0, -1):
            day_date = str(today - datetime.timedelta(days=d))
            noise = random.uniform(-1.5, 1.8)
            val = round(base_val + noise + (14 - d) * 0.15, 2)
            save_index_record(
                calc_date=day_date,
                headline=val,
                t1=round(val * 1.55, 2),
                t7=round(val * 1.20, 2),
                t15=round(val * 1.03, 2),
                t30=round(val * 0.98, 2),
                t45=round(val * 0.91, 2),
                sample_size=32
            )
