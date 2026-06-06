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
MIN_ENTRY_LTP   = 5.0
MIN_OI_CHANGE   = 100000
MIN_OI_CHANGE_PCT = 1.0
MIN_VOLUME_CHANGE = 100000
MIN_SIGNAL_SCORE = 70

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


def _pct_change(current_value, previous_value):
    return calculate_percent_change(current_value, previous_value)


def _confidence(score):
    if score >= 85:
        return "High"
    if score >= 70:
        return "Medium"
    return "Low"


def _score_entry(metrics, mode):
    score = 0
    reasons = []

    if mode == "fresh" and metrics["buildup"] == "Long Build-up":
        score += 20
        reasons.append("long buildup")
    elif mode == "cover" and metrics["buildup"] == "Short Covering":
        score += 20
        reasons.append("short covering")

    if metrics["price_change"] > 0:
        score += 10
        reasons.append("price up")

    if abs(metrics["oi_change"]) >= MIN_OI_CHANGE:
        score += 15
        reasons.append("OI change")

    if abs(metrics["oi_change_pct"]) >= MIN_OI_CHANGE_PCT:
        score += 10
        reasons.append("OI %")

    if metrics["volume_change"] >= MIN_VOLUME_CHANGE:
        score += 10
        reasons.append("volume")

    if metrics["delta_abs"] >= DELTA_EXIT_ABS:
        score += 15
        reasons.append("delta strong")

    if metrics["delta_change"] >= (DELTA_FRESH if mode == "fresh" else DELTA_MOMENTUM):
        score += 10
        reasons.append("delta rising")

    if metrics["gamma_change"] >= (GAMMA_FRESH if mode == "fresh" else GAMMA_MOMENTUM):
        score += 10
        reasons.append("gamma rising")

    return score, ", ".join(reasons)


def _option_metrics(curr, prev, opt):
    prefix = "call" if opt == "CE" else "put"
    price_col = f"{prefix}_price"
    oi_col = f"{prefix}_oi"
    volume_col = f"{prefix}_volume"
    delta_col = f"{prefix}_delta"
    gamma_col = f"{prefix}_gamma"

    price_change = curr[price_col] - prev[price_col]
    oi_change = curr[oi_col] - prev[oi_col]
    volume_change = curr[volume_col] - prev[volume_col]
    delta_change = _pct_change(abs(curr[delta_col]), abs(prev[delta_col]))
    gamma_change = _pct_change(curr[gamma_col], prev[gamma_col])
    oi_change_pct = _pct_change(curr[oi_col], prev[oi_col])

    return {
        "opt": opt,
        "price": curr[price_col],
        "price_change": price_change,
        "oi_change": oi_change,
        "oi_change_pct": oi_change_pct,
        "volume_change": volume_change,
        "delta": curr[delta_col],
        "delta_abs": abs(curr[delta_col]),
        "delta_change": delta_change,
        "gamma": curr[gamma_col],
        "gamma_change": gamma_change,
        "buildup": _classify(price_change, oi_change)
    }


def _passes_entry(metrics, mode):
    if metrics["price"] < MIN_ENTRY_LTP:
        return False

    if not _can_enter(metrics["delta"]):
        return False

    if metrics["volume_change"] < MIN_VOLUME_CHANGE:
        return False

    if abs(metrics["oi_change"]) < MIN_OI_CHANGE:
        return False

    if abs(metrics["oi_change_pct"]) < MIN_OI_CHANGE_PCT:
        return False

    if mode == "fresh":
        return (
            metrics["buildup"] == "Long Build-up" and
            metrics["delta_change"] >= DELTA_FRESH and
            metrics["gamma_change"] >= GAMMA_FRESH
        )

    return (
        metrics["buildup"] == "Short Covering" and
        metrics["delta_change"] >= DELTA_MOMENTUM and
        metrics["gamma_change"] >= GAMMA_MOMENTUM
    )


def _append_signal(signals, df_s, index, metrics, setup, bmin, tlbl, mode):
    score, reason = _score_entry(metrics, mode)

    if score < MIN_SIGNAL_SCORE:
        return

    ltp = round(float(metrics["price"]), 2)
    sl = round(ltp * (1 - SL_PCT), 2)
    tgt = round(ltp * (1 + TARGET_PCT), 2)
    oc, ex_ltp, ex_time, pnl = _resolve_outcome(
        df_s,
        index,
        metrics["opt"],
        sl,
        tgt,
        bmin
    )

    signals.append({
        "time": tlbl,
        "setup": setup,
        "option": metrics["opt"],
        "entry_ltp": ltp,
        "sl": sl,
        "target": tgt,
        "delta": round(float(metrics["delta"]), 4),
        "delta_chg": float(metrics["delta_change"]),
        "gamma": round(float(metrics["gamma"]), 6),
        "gamma_chg": float(metrics["gamma_change"]),
        "buildup": metrics["buildup"],
        "oi_change": int(metrics["oi_change"]),
        "oi_change_pct": float(metrics["oi_change_pct"]),
        "price_change": round(float(metrics["price_change"]), 2),
        "volume_change": int(metrics["volume_change"]),
        "score": int(score),
        "confidence": _confidence(score),
        "reason": reason,
        "outcome": oc,
        "exit_ltp": float(ex_ltp),
        "exit_time": ex_time,
        "pnl_pct": float(pnl)
    })


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

        ce_metrics = _option_metrics(curr, prev, "CE")
        pe_metrics = _option_metrics(curr, prev, "PE")

        if _passes_entry(ce_metrics, "fresh"):
            _append_signal(signals, df_s, i, ce_metrics, "CE Long", bmin, tlbl, "fresh")

        if _passes_entry(pe_metrics, "fresh"):
            _append_signal(signals, df_s, i, pe_metrics, "PE Long", bmin, tlbl, "fresh")

        if _passes_entry(ce_metrics, "cover"):
            _append_signal(signals, df_s, i, ce_metrics, "CE Short Cover", bmin, tlbl, "cover")

        if _passes_entry(pe_metrics, "cover"):
            _append_signal(signals, df_s, i, pe_metrics, "PE Short Cover", bmin, tlbl, "cover")

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
        net_pnl = float(round(sum(s["pnl_pct"] for s in closed), 1))

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
