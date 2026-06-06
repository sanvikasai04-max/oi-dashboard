from fastapi import APIRouter
from sqlalchemy.orm import Session
import pandas as pd

from app.database import (
    SessionLocal,
    OISnapshot
)

from app.calculations import (
    get_atm_strike,
    generate_oi_table,
    generate_greek_spikes,
    calculate_percent_change,
    filter_market_session
)
from app.config import (
    get_data_date,
    get_data_iso_date,
    STRIKE_STEP,
    TRACK_EXPIRY
)

router = APIRouter()

# =========================================
# ENTRY SIGNAL THRESHOLDS
# =========================================

DELTA_FRESH     = 15.0   # % - CE Long / PE Long
GAMMA_FRESH     = 15.0
DELTA_MOMENTUM  = 20.0   # % - Short Cover setups
GAMMA_MOMENTUM  = 20.0
SL_PCT          = 0.30   # 30% below entry LTP
TARGET_PCT      = 0.50   # 50% above entry LTP
DELTA_EXIT_ABS  = 0.40   # exit if |delta| drops below this

# =========================================
# HELPERS
# =========================================

def _classify(price_chg, oi_chg):
    if price_chg > 0 and oi_chg > 0:   return "Long Build-up"
    if price_chg < 0 and oi_chg > 0:   return "Short Build-up"
    if price_chg > 0 and oi_chg < 0:   return "Short Covering"
    if price_chg < 0 and oi_chg < 0:   return "Long Unwinding"
    return "No Signal"


def _bucket_label(ts, bmin):
    from datetime import timedelta
    s = ts.replace(minute=(ts.minute // bmin) * bmin, second=0, microsecond=0)
    e = s + timedelta(minutes=bmin)
    return f"{s.strftime('%H:%M')} - {e.strftime('%H:%M')}"


def _resolve_outcome(df_s, entry_idx, opt, sl, target, bmin):
    """Walk forward from entry_idx to find first SL / target / delta-exit hit."""
    price_col = "call_price" if opt == "CE" else "put_price"
    delta_col = "call_delta" if opt == "CE" else "put_delta"
    entry_ltp = df_s.iloc[entry_idx][price_col]

    for j in range(entry_idx + 1, len(df_s)):
        row = df_s.iloc[j]
        ltp   = row[price_col]
        d_abs = abs(row[delta_col])
        tlbl  = _bucket_label(row["bucket"], bmin)

        pnl = round(((ltp - entry_ltp) / entry_ltp) * 100, 1)

        if ltp <= sl:
            return "SL Hit", round(ltp, 2), tlbl, pnl
        if ltp >= target:
            return "Target Hit", round(ltp, 2), tlbl, pnl
        if d_abs < DELTA_EXIT_ABS:
            return "Delta Exit", round(ltp, 2), tlbl, pnl

    last    = df_s.iloc[-1]
    ltp     = last[price_col]
    pnl     = round(((ltp - entry_ltp) / entry_ltp) * 100, 1)
    return "Open", round(ltp, 2), _bucket_label(last["bucket"], bmin), pnl


def _can_enter(delta):
    return abs(delta) >= DELTA_EXIT_ABS


def detect_entries(df, strike, interval_name):
    """
    Scan bucketed data for a single strike and return entry signals
    with SL, target, outcome, and P&L.
    """
    from app.config import INTERVAL_MAP
    lookback   = INTERVAL_MAP[interval_name]
    bmin       = lookback * 5

    df_s = df[df["strike"] == strike].copy()
    if df_s.empty:
        return []

    df_s["timestamp"] = pd.to_datetime(df_s["timestamp"])
    df_s = filter_market_session(df_s)

    if df_s.empty:
        return []

    df_s["bucket"]    = df_s["timestamp"].dt.floor(f"{bmin}min")

    # drop blank rows
    df_s = df_s[~(
        (df_s["call_price"] == 0) &
        (df_s["put_price"]  == 0) &
        ((df_s["call_oi"].fillna(0) + df_s["put_oi"].fillna(0)) == 0)
    )]

    df_s = (df_s
            .sort_values(["bucket", "timestamp"])
            .drop_duplicates(subset=["bucket"], keep="last")
            .sort_values("bucket")
            .reset_index(drop=True))

    signals = []

    for i in range(1, len(df_s)):
        curr = df_s.iloc[i]
        prev = df_s.iloc[i - 1]
        tlbl = _bucket_label(curr["bucket"], bmin)

        # --- CE metrics ---
        ce_build = _classify(
            curr["call_price"] - prev["call_price"],
            curr["call_oi"]    - prev["call_oi"]
        )
        ce_dc = calculate_percent_change(abs(curr["call_delta"]), abs(prev["call_delta"]))
        ce_gc = calculate_percent_change(curr["call_gamma"],      prev["call_gamma"])

        # --- PE metrics ---
        pe_build = _classify(
            curr["put_price"] - prev["put_price"],
            curr["put_oi"]    - prev["put_oi"]
        )
        pe_dc = calculate_percent_change(abs(curr["put_delta"]), abs(prev["put_delta"]))
        pe_gc = calculate_percent_change(curr["put_gamma"],      prev["put_gamma"])

        # ---- Setup 1: CE Long Fresh ----
        if _can_enter(curr["call_delta"]) and ce_dc >= DELTA_FRESH and ce_gc >= GAMMA_FRESH and ce_build == "Long Build-up":
            ltp    = round(curr["call_price"], 2)
            sl     = round(ltp * (1 - SL_PCT), 2)
            tgt    = round(ltp * (1 + TARGET_PCT), 2)
            oc, ex_ltp, ex_time, pnl = _resolve_outcome(df_s, i, "CE", sl, tgt, bmin)
            signals.append({
                "time": tlbl, "setup": "CE Long", "option": "CE",
                "entry_ltp": ltp, "sl": sl, "target": tgt,
                "delta": round(curr["call_delta"], 4), "delta_chg": ce_dc,
                "gamma": round(curr["call_gamma"], 6), "gamma_chg": ce_gc,
                "buildup": ce_build,
                "outcome": oc, "exit_ltp": ex_ltp, "exit_time": ex_time, "pnl_pct": pnl
            })

        # ---- Setup 2: PE Long Fresh ----
        if _can_enter(curr["put_delta"]) and pe_dc >= DELTA_FRESH and pe_gc >= GAMMA_FRESH and pe_build == "Long Build-up":
            ltp    = round(curr["put_price"], 2)
            sl     = round(ltp * (1 - SL_PCT), 2)
            tgt    = round(ltp * (1 + TARGET_PCT), 2)
            oc, ex_ltp, ex_time, pnl = _resolve_outcome(df_s, i, "PE", sl, tgt, bmin)
            signals.append({
                "time": tlbl, "setup": "PE Long", "option": "PE",
                "entry_ltp": ltp, "sl": sl, "target": tgt,
                "delta": round(curr["put_delta"], 4), "delta_chg": pe_dc,
                "gamma": round(curr["put_gamma"], 6), "gamma_chg": pe_gc,
                "buildup": pe_build,
                "outcome": oc, "exit_ltp": ex_ltp, "exit_time": ex_time, "pnl_pct": pnl
            })

        # ---- Setup 3: CE Short Cover ----
        if _can_enter(curr["call_delta"]) and ce_dc >= DELTA_MOMENTUM and ce_gc >= GAMMA_MOMENTUM and ce_build == "Short Covering":
            ltp    = round(curr["call_price"], 2)
            sl     = round(ltp * (1 - SL_PCT), 2)
            tgt    = round(ltp * (1 + TARGET_PCT), 2)
            oc, ex_ltp, ex_time, pnl = _resolve_outcome(df_s, i, "CE", sl, tgt, bmin)
            signals.append({
                "time": tlbl, "setup": "CE Short Cover", "option": "CE",
                "entry_ltp": ltp, "sl": sl, "target": tgt,
                "delta": round(curr["call_delta"], 4), "delta_chg": ce_dc,
                "gamma": round(curr["call_gamma"], 6), "gamma_chg": ce_gc,
                "buildup": ce_build,
                "outcome": oc, "exit_ltp": ex_ltp, "exit_time": ex_time, "pnl_pct": pnl
            })

        # ---- Setup 4: PE Short Cover ----
        if _can_enter(curr["put_delta"]) and pe_dc >= DELTA_MOMENTUM and pe_gc >= GAMMA_MOMENTUM and pe_build == "Short Covering":
            ltp    = round(curr["put_price"], 2)
            sl     = round(ltp * (1 - SL_PCT), 2)
            tgt    = round(ltp * (1 + TARGET_PCT), 2)
            oc, ex_ltp, ex_time, pnl = _resolve_outcome(df_s, i, "PE", sl, tgt, bmin)
            signals.append({
                "time": tlbl, "setup": "PE Short Cover", "option": "PE",
                "entry_ltp": ltp, "sl": sl, "target": tgt,
                "delta": round(curr["put_delta"], 4), "delta_chg": pe_dc,
                "gamma": round(curr["put_gamma"], 6), "gamma_chg": pe_gc,
                "buildup": pe_build,
                "outcome": oc, "exit_ltp": ex_ltp, "exit_time": ex_time, "pnl_pct": pnl
            })

    return signals


# =========================================
# ATM API
# =========================================

@router.get("/api/atm")
def get_atm_data(interval: str = "5m"):

    db: Session = SessionLocal()

    try:
        rows = db.query(OISnapshot).filter(
            OISnapshot.expiry == TRACK_EXPIRY
        ).all()

        if not rows:
            return {"error": "No data found"}

        data = []
        for row in rows:
            data.append({
                "timestamp": row.timestamp,
                "strike": row.strike,
                "spot": row.spot,
                "call_ltp": row.call_price,
                "put_ltp": row.put_price,
                "call_oi": row.call_oi,
                "put_oi": row.put_oi,
                "call_price": row.call_price,
                "put_price": row.put_price,
                "call_volume": row.call_volume,
                "put_volume": row.put_volume,
                "call_delta": row.call_delta,
                "put_delta": row.put_delta,
                "call_gamma": row.call_gamma,
                "put_gamma": row.put_gamma,
                "call_iv": row.call_iv,
                "put_iv": row.put_iv
            })

        df = pd.DataFrame(data)

        if len(df) > 0:
            print(f"\n=== ATM Route Debug ===")
            print(f"Total records: {len(df)}")
            print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
            print(f"Unique strikes: {sorted(df['strike'].unique())}")
            print("===\n")

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        data_iso_date = get_data_iso_date()

        if data_iso_date:
            df = df[df["timestamp"].dt.strftime("%Y-%m-%d") == data_iso_date]

        df = filter_market_session(df)

        if df.empty:
            return {"error": "No data found for selected trading session"}

        df = df.sort_values("timestamp")

        latest = df.iloc[-1]
        spot   = latest["spot"]
        atm    = get_atm_strike(spot)

        ce_data = generate_oi_table(history_df=df, strike=atm, option_type="CE", interval_name=interval)
        pe_data = generate_oi_table(history_df=df, strike=atm, option_type="PE", interval_name=interval)

        return {
            "spot": spot,
            "atm": atm,
            "interval": interval,
            "last_update": str(latest["timestamp"]),
            "earliest_update": str(df.iloc[0]["timestamp"]),
            "data_date": get_data_date(),
            "ce_data": ce_data,
            "pe_data": pe_data
        }

    finally:
        db.close()


# =========================================
# GREEKS API - now also returns entry signals
# =========================================

@router.get("/api/greeks")
def get_greeks_data(
    interval: str = "5m",
    strike: int = None
):

    db: Session = SessionLocal()

    try:
        rows = db.query(OISnapshot).filter(
            OISnapshot.expiry == TRACK_EXPIRY
        ).all()

        if not rows:
            return {"error": "No data found"}

        data = []
        for row in rows:
            data.append({
                "timestamp":   row.timestamp,
                "strike":      row.strike,
                "spot":        row.spot,
                "call_oi":     row.call_oi,
                "put_oi":      row.put_oi,
                "call_price":  row.call_price,
                "put_price":   row.put_price,
                "call_volume": row.call_volume,
                "put_volume":  row.put_volume,
                "call_delta":  row.call_delta,
                "put_delta":   row.put_delta,
                "call_gamma":  row.call_gamma,
                "put_gamma":   row.put_gamma,
                "call_iv":     row.call_iv,
                "put_iv":      row.put_iv
            })

        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        data_iso_date = get_data_iso_date()

        if data_iso_date:
            df = df[df["timestamp"].dt.strftime("%Y-%m-%d") == data_iso_date]

        df = filter_market_session(df)

        if df.empty:
            return {"error": "No data found for selected trading session"}

        df = df.sort_values("timestamp")

        opening      = df.iloc[0]
        latest       = df.iloc[-1]
        spot         = latest["spot"]
        opening_spot = opening["spot"]
        opening_atm  = get_atm_strike(opening_spot)

        strike_options = [
            opening_atm + i
            for i in range(-500, 501, STRIKE_STEP)
        ]

        if strike is None or strike not in strike_options:
            strike = opening_atm

        # ---- existing spike tables ----
        ce_spikes = generate_greek_spikes(
            history_df=df, strike=strike, option_type="CE", interval_name=interval
        )
        pe_spikes = generate_greek_spikes(
            history_df=df, strike=strike, option_type="PE", interval_name=interval
        )

        # ---- NEW: entry signals for this strike ----
        entry_signals = detect_entries(df, strike, interval)

        # ---- summary for the scorecard ----
        closed = [s for s in entry_signals if s["outcome"] != "Open"]
        hits   = [s for s in entry_signals if s["outcome"] == "Target Hit"]
        sls    = [s for s in entry_signals if s["outcome"] == "SL Hit"]
        d_exits= [s for s in entry_signals if s["outcome"] == "Delta Exit"]
        net_pnl = round(sum(s["pnl_pct"] for s in closed), 1)

        return {
            "spot":          spot,
            "opening_atm":   opening_atm,
            "strike":        strike,
            "strike_options":strike_options,
            "interval":      interval,
            "last_update":   str(latest["timestamp"]),
            "earliest_update": str(opening["timestamp"]),
            "data_date":     get_data_date(),
            "ce_spikes":     ce_spikes,
            "pe_spikes":     pe_spikes,
            # ---- new fields ----
            "entry_signals": entry_signals,
            "entry_summary": {
                "total":        len(entry_signals),
                "target_hits":  len(hits),
                "sl_hits":      len(sls),
                "delta_exits":  len(d_exits),
                "open":         len(entry_signals) - len(closed),
                "net_pnl_pct":  net_pnl
            }
        }

    finally:
        db.close()
