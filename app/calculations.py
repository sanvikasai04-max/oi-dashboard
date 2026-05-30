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
    # CREATE 5-MIN BUCKET
    # =====================================

    df["bucket"] = (
        df["timestamp"]
        .dt.floor("5min")
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

    current_bucket = now.floor("5min")

    grouped = grouped[
        grouped["bucket"] < current_bucket
    ]
    rows = []

    # =====================================
    # LOOP
    # =====================================

    for i in range(lookback, len(grouped)):

        current = grouped.iloc[i]

        # =================================
        # EXACT LOOKBACK ROW
        # =================================

        past = grouped.iloc[i - lookback]

        # =================================
        # OPTION TYPE
        # =================================

        if option_type == "CE":

            price_change = (
                current["call_price_last"]
                - current["call_price_first"]
            )

            oi_change = (
                current["call_oi_last"]
                - current["call_oi_first"]
            )
            prev_bucket = grouped.iloc[i - 1]

            volume_change = (
                current["call_volume_last"]
                - prev_bucket["call_volume_last"]
            )
            delta = current["call_delta_last"]

            prev_delta = past["call_delta_last"]

            gamma = current["call_gamma_last"]

            prev_gamma = past["call_gamma_last"]

            iv = current["call_iv_last"]

            prev_iv = past["call_iv_last"]
        else:

            price_change = (
                current["put_price_last"]
                - current["put_price_first"]
            )

            oi_change = (
                current["put_oi_last"]
                - current["put_oi_first"]
            )

            prev_bucket = grouped.iloc[i - 1]

            volume_change = (
                current["put_volume_last"]
                - prev_bucket["put_volume_last"]
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

        delta_change = 0

        gamma_change = 0

        iv_change = 0

        if abs(prev_delta) > 0.01:

            delta_change = round(

                ((delta - prev_delta)
                / abs(prev_delta)) * 100,

                2

            )

        if abs(prev_gamma) > 0.00001:

            gamma_change = round(

                ((gamma - prev_gamma)
                / abs(prev_gamma)) * 100,

                2

            )

        if prev_iv != 0:

            iv_change = round(

                ((iv - prev_iv)
                / abs(prev_iv)) * 100,

                2

            )

        # =================================
        # APPEND ROW
        # =================================

        rows.append({

            "time": (
                f"{past['bucket'].strftime('%H:%M')}"
                f" - "
                f"{current['bucket'].strftime('%H:%M')}"
            ),

            "buildup": buildup,

            "volume": format_volume(
                volume_change
            ),

            "delta": round(delta, 2),

            "delta_change": delta_change,

            "gamma": round(gamma, 4),

            "gamma_change": gamma_change,

            "iv": round(iv, 2),

            "iv_change": iv_change

        })

    # =====================================
    # LATEST FIRST
    # =====================================

    rows.reverse()

    return rows