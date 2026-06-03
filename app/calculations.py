import pandas as pd
import datetime as dt

from app.config import (
    STRIKE_STEP,
    INTERVAL_MAP
)

# =========================================
# FORMAT VOLUME
# =========================================

def format_volume(num):

    num = abs(num)

    if num >= 10000000:
        return f"{num/10000000:.2f} Cr"

    elif num >= 100000:
        return f"{num/100000:.2f} L"

    elif num >= 1000:
        return f"{num/1000:.2f} K"

    return str(int(num))

# =========================================
# CLASSIFY BUILDUP
# =========================================

def classify_build_up(price_change, oi_change):

    if price_change > 0 and oi_change > 0:

        return "Long Build-up"

    elif price_change < 0 and oi_change > 0:

        return "Short Build-up"

    elif price_change > 0 and oi_change < 0:

        return "Short Covering"

    elif price_change < 0 and oi_change < 0:

        return "Long Unwinding"

    return "No Signal"

# =========================================
# CALCULATE PERCENT CHANGE
# =========================================

def calculate_percent_change(current_value, previous_value):

    if current_value == previous_value:

        return 0

    if previous_value == 0:

        return 0

    return round(
        ((current_value - previous_value)
        / abs(previous_value)) * 100,
        2
    )

# =========================================
# GET ATM STRIKE
# =========================================

def get_atm_strike(spot):

    atm = int((spot + (STRIKE_STEP / 2))
              / STRIKE_STEP) * STRIKE_STEP

    return atm

# =========================================
# GET ITM OTM STRIKES
# =========================================

def get_itm_otm_strikes(atm):

    itm = atm - STRIKE_STEP

    otm = atm + STRIKE_STEP

    return itm, otm

# =========================================
# FORMAT TIME LABEL
# =========================================

def format_bucket_time(ts, lookback):

    interval_minutes = lookback * 5

    aligned_start = ts.replace(
        minute=(ts.minute // interval_minutes)
               * interval_minutes,
        second=0,
        microsecond=0
    )

    aligned_end = aligned_start + dt.timedelta(
        minutes=interval_minutes
    )

    return (
        f"{aligned_start.strftime('%H:%M')}"
        f" - "
        f"{aligned_end.strftime('%H:%M')}"
    )

# =========================================
# GENERATE TIMEFRAME TABLE
# =========================================

def generate_oi_table(
    history_df,
    strike,
    option_type,
    interval_name
):

    # =====================================
    # INTERVAL LOOKBACK
    # =====================================

    lookback = INTERVAL_MAP[interval_name]

    bucket_minutes = lookback * 5

    # =====================================
    # FILTER STRIKE
    # =====================================

    df = history_df[
        history_df["strike"] == strike
    ].copy()

    if df.empty:
        return []

    # =====================================
    # TIMESTAMP
    # =====================================

    df["timestamp"] = pd.to_datetime(
        df["timestamp"]
    )

    df = df.sort_values("timestamp")

    # =====================================
    # CREATE SELECTED TIMEFRAME BUCKET
    # =====================================

    df["bucket"] = (
        df["timestamp"]
        .dt.floor(f"{bucket_minutes}min")
    )

    # =====================================
    # DROP BAD SNAPSHOTS AND PICK BEST ROW PER BUCKET
    # =====================================

    df["total_oi"] = (
        df["call_oi"].fillna(0) +
        df["put_oi"].fillna(0)
    )
    df["total_volume"] = (
        df["call_volume"].fillna(0) +
        df["put_volume"].fillna(0)
    )

    df = df[~(
        (df["call_price"] == 0) &
        (df["put_price"] == 0) &
        (df["total_oi"] == 0)
    )]

    df = df.sort_values(
        ["bucket", "total_oi", "total_volume", "timestamp"],
        ascending=[True, False, False, False]
    )
    df = df.drop_duplicates(
        subset=["bucket"],
        keep="first"
    )

    # =====================================
    # KEEP LAST ROW PER BUCKET
    # =====================================

    grouped = (
        df.groupby("bucket")
        .agg({

            "call_price": ["first", "last"],
            "put_price": ["first", "last"],

            "call_oi": ["first", "last"],
            "put_oi": ["first", "last"],

            "call_volume": ["first", "last"],
            "put_volume": ["first", "last"],

            "call_delta": "last",
            "put_delta": "last",

            "call_gamma": "last",
            "put_gamma": "last",

            "call_iv": "last",
            "put_iv": "last"

        })
    )

    grouped.columns = [

        "_".join(col).strip("_")

        for col in grouped.columns.values

    ]

    grouped = grouped.reset_index()
    now = pd.Timestamp.now()

    current_bucket = now.floor(f"{bucket_minutes}min")

    grouped = grouped[
        grouped["bucket"] < current_bucket
    ]
    rows = []

    # =====================================
    # LOOP
    # =====================================

    for i in range(len(grouped)):

        current = grouped.iloc[i]

        # =================================
        # PREVIOUS COMPLETED TIMEFRAME BUCKET
        # =================================

        if i == 0:
            past = current
        else:
            past = grouped.iloc[i - 1]

        # =================================
        # OPTION TYPE
        # =================================

        if option_type == "CE":

            if i == 0:
                price_change = 0
                oi_change = 0
                volume_change = 0
                fresh_entry_ratio = 0
            else:
                prev_bucket = grouped.iloc[i - 1]
                price_change = (
                    current["call_price_last"]
                    - prev_bucket["call_price_last"]
                )
                oi_change = (
                    current["call_oi_last"]
                    - prev_bucket["call_oi_last"]
                )
                volume_change = (
                    current["call_volume_last"]
                    - prev_bucket["call_volume_last"]
                )
                fresh_entry_ratio = (
                    round((oi_change / volume_change) * 100, 2)
                    if volume_change else 0
                )

            delta = current["call_delta_last"]
            prev_delta = past["call_delta_last"]
            gamma = current["call_gamma_last"]
            prev_gamma = past["call_gamma_last"]
            iv = current["call_iv_last"]
            prev_iv = past["call_iv_last"]

        else:

            if i == 0:
                price_change = 0
                oi_change = 0
                volume_change = 0
                fresh_entry_ratio = 0
            else:
                prev_bucket = grouped.iloc[i - 1]
                price_change = (
                    current["put_price_last"]
                    - prev_bucket["put_price_last"]
                )
                oi_change = (
                    current["put_oi_last"]
                    - prev_bucket["put_oi_last"]
                )
                volume_change = (
                    current["put_volume_last"]
                    - prev_bucket["put_volume_last"]
                )
                fresh_entry_ratio = (
                    round((oi_change / volume_change) * 100, 2)
                    if volume_change else 0
                )

            delta = current["put_delta_last"]
            prev_delta = past["put_delta_last"]
            gamma = current["put_gamma_last"]
            prev_gamma = past["put_gamma_last"]
            iv = current["put_iv_last"]
            prev_iv = past["put_iv_last"]

        # =================================
        # BUILDUP
        # =================================

        buildup = classify_build_up(
            price_change,
            oi_change
        )

        # =================================
        # RATE OF CHANGE
        # =================================

        display_delta = round(delta, 2)

        display_prev_delta = round(prev_delta, 2)

        display_gamma = round(gamma, 4)

        display_prev_gamma = round(prev_gamma, 4)

        display_iv = round(iv, 2)

        display_prev_iv = round(prev_iv, 2)

        delta_change = calculate_percent_change(
            display_delta,
            display_prev_delta
        )

        gamma_change = calculate_percent_change(
            display_gamma,
            display_prev_gamma
        )

        iv_change = calculate_percent_change(
            display_iv,
            display_prev_iv
        )

        # =================================
        # GET LTP
        # =================================

        if option_type == "CE":
            ltp = current["call_price_last"]
        else:
            ltp = current["put_price_last"]

        # =================================
        # APPEND ROW
        # =================================

        rows.append({

            "time": format_bucket_time(
                current["bucket"],
                lookback
            ),

            "ltp": round(ltp, 2),

            "buildup": buildup,

            "volume": format_volume(
                volume_change
            ),

            "oi_change": int(oi_change),
            "fresh_entry_ratio": fresh_entry_ratio,

            "delta": display_delta,

            "delta_change": delta_change,

            "gamma": display_gamma,

            "gamma_change": gamma_change,

            "iv": display_iv,

            "iv_change": iv_change

        })

    # =====================================
    # LATEST FIRST
    # =====================================

    rows.reverse()

    return rows
