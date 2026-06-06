from fastapi import APIRouter
from sqlalchemy.orm import Session
import pandas as pd

from app.calculations import (
    calculate_percent_change,
    filter_market_session,
    get_atm_strike
)
from app.config import (
    get_data_date,
    get_data_iso_date,
    TRACK_EXPIRY
)
from app.database import OISnapshot, SessionLocal

router = APIRouter()

INTERVAL_MINUTES = 5
MIN_ENTRY_LTP = 5.0
MIN_DELTA_ABS = 0.18
MIN_GAMMA = 0.0015
MIN_DELTA_CHANGE = 15.0
MIN_GAMMA_CHANGE = 10.0
MIN_OI_CHANGE = 100000
MIN_OI_CHANGE_PCT = 0.3
MIN_PRICE_CHANGE_PCT = 15.0
MIN_SIGNAL_SCORE = 75
DELTA_EXIT_ABS = 0.14


def _fetch_session_df():
    db: Session = SessionLocal()

    try:
        rows = db.query(OISnapshot).filter(
            OISnapshot.expiry == TRACK_EXPIRY
        ).all()

        data = []
        for row in rows:
            data.append({
                "timestamp": row.timestamp,
                "strike": row.strike,
                "spot": row.spot,
                "call_price": row.call_price,
                "put_price": row.put_price,
                "call_oi": row.call_oi,
                "put_oi": row.put_oi,
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

        if df.empty:
            return df

        df["timestamp"] = pd.to_datetime(df["timestamp"])

        data_iso_date = get_data_iso_date()
        if data_iso_date:
            df = df[df["timestamp"].dt.strftime("%Y-%m-%d") == data_iso_date]

        df = filter_market_session(df)
        return df.sort_values(["strike", "timestamp"]).reset_index(drop=True)

    finally:
        db.close()


def _classify(price_change, oi_change):
    if price_change > 0 and oi_change > 0:
        return "Long Build-up"
    if price_change < 0 and oi_change > 0:
        return "Short Build-up"
    if price_change > 0 and oi_change < 0:
        return "Short Covering"
    if price_change < 0 and oi_change < 0:
        return "Long Unwinding"
    return "No Signal"


def _market_direction(df):
    spot = (
        df.sort_values("timestamp")
        .drop_duplicates("timestamp")
        [["timestamp", "spot"]]
        .reset_index(drop=True)
    )

    spot["spot_3_change"] = spot["spot"] - spot["spot"].shift(3)
    spot["spot_5_change"] = spot["spot"] - spot["spot"].shift(5)

    direction_by_time = {}
    for row in spot.itertuples():
        if pd.isna(row.spot_3_change):
            direction = "Neutral"
        elif row.spot_3_change >= 18 or row.spot_5_change >= 28:
            direction = "Bullish"
        elif row.spot_3_change <= -18 or row.spot_5_change <= -28:
            direction = "Bearish"
        else:
            direction = "Neutral"

        direction_by_time[row.timestamp] = {
            "direction": direction,
            "spot_3_change": 0 if pd.isna(row.spot_3_change) else float(round(row.spot_3_change, 2)),
            "spot_5_change": 0 if pd.isna(row.spot_5_change) else float(round(row.spot_5_change, 2))
        }

    return direction_by_time


def _strike_zone(option_type, strike, atm, direction, spot_change):
    if direction == "Bullish" and option_type == "CE":
        if strike == atm:
            return "ATM CE"
        if strike in (atm - 50, atm - 100):
            return "ITM CE"
        if strike == atm + 50 and spot_change >= 28:
            return "Breakout OTM CE"

    if direction == "Bearish" and option_type == "PE":
        if strike in (atm - 50, atm - 100):
            return "OTM PE"
        if strike == atm and spot_change <= -28:
            return "Breakdown ATM PE"

    return None


def _option_metrics(curr, prev, option_type):
    prefix = "call" if option_type == "CE" else "put"
    price = float(curr[f"{prefix}_price"])
    prev_price = float(prev[f"{prefix}_price"])
    oi = float(curr[f"{prefix}_oi"])
    prev_oi = float(prev[f"{prefix}_oi"])
    volume = float(curr[f"{prefix}_volume"])
    prev_volume = float(prev[f"{prefix}_volume"])
    delta = float(curr[f"{prefix}_delta"])
    prev_delta = float(prev[f"{prefix}_delta"])
    gamma = float(curr[f"{prefix}_gamma"])
    prev_gamma = float(prev[f"{prefix}_gamma"])

    price_change = price - prev_price
    oi_change = oi - prev_oi

    return {
        "option_type": option_type,
        "price": price,
        "price_change": price_change,
        "price_change_pct": calculate_percent_change(price, prev_price),
        "oi_change": oi_change,
        "oi_change_pct": calculate_percent_change(oi, prev_oi),
        "volume_change": volume - prev_volume,
        "delta": delta,
        "delta_abs": abs(delta),
        "delta_change": calculate_percent_change(abs(delta), abs(prev_delta)),
        "gamma": gamma,
        "gamma_change": calculate_percent_change(gamma, prev_gamma),
        "buildup": _classify(price_change, oi_change)
    }


def _score_signal(metrics, zone, direction):
    score = 0
    reasons = []

    if direction in ("Bullish", "Bearish"):
        score += 15
        reasons.append(direction.lower())

    if zone:
        score += 15 if "OTM" not in zone or "Breakout" not in zone else 10
        reasons.append(zone)

    if metrics["buildup"] in ("Long Build-up", "Short Covering"):
        score += 15
        reasons.append(metrics["buildup"])

    if metrics["price_change_pct"] >= MIN_PRICE_CHANGE_PCT:
        score += 10
        reasons.append("price momentum")

    if abs(metrics["oi_change"]) >= MIN_OI_CHANGE:
        score += 10
        reasons.append("OI confirmation")

    if abs(metrics["oi_change_pct"]) >= MIN_OI_CHANGE_PCT:
        score += 10
        reasons.append("OI percent")

    if metrics["delta_abs"] >= MIN_DELTA_ABS:
        score += 10
        reasons.append("delta active")

    if metrics["delta_change"] >= MIN_DELTA_CHANGE:
        score += 10
        reasons.append("delta spike")

    if metrics["gamma"] >= MIN_GAMMA and metrics["gamma_change"] >= MIN_GAMMA_CHANGE:
        score += 10
        reasons.append("gamma acceleration")

    if metrics["volume_change"] > 0:
        score += 5
        reasons.append("volume added")

    return score, ", ".join(reasons)


def _build_candles(df, strike, option_type):
    price_col = "call_price" if option_type == "CE" else "put_price"
    delta_col = "call_delta" if option_type == "CE" else "put_delta"
    gamma_col = "call_gamma" if option_type == "CE" else "put_gamma"
    oi_col = "call_oi" if option_type == "CE" else "put_oi"

    part = df[df["strike"] == strike].copy()
    if part.empty:
        return []

    part["bucket"] = part["timestamp"].dt.floor(f"{INTERVAL_MINUTES}min")
    grouped = part.groupby("bucket").agg({
        price_col: ["first", "max", "min", "last"],
        "spot": "last",
        delta_col: "last",
        gamma_col: "last",
        oi_col: "last"
    })
    grouped.columns = ["open", "high", "low", "close", "spot", "delta", "gamma", "oi"]
    grouped = grouped.reset_index().sort_values("bucket")

    candles = []
    for row in grouped.itertuples():
        candles.append({
            "time": row.bucket.strftime("%H:%M"),
            "open": round(float(row.open), 2),
            "high": round(float(row.high), 2),
            "low": round(float(row.low), 2),
            "close": round(float(row.close), 2),
            "spot": round(float(row.spot), 2),
            "delta": round(float(row.delta), 4),
            "gamma": round(float(row.gamma), 6),
            "oi": int(row.oi)
        })

    return candles


def _risk_plan(candles, entry_price, entry_time, zone):
    entry_index = 0
    for i, candle in enumerate(candles):
        if candle["time"] <= entry_time[:5]:
            entry_index = i
    start = max(0, entry_index - 5)
    ranges = [
        max(0.05, candle["high"] - candle["low"])
        for candle in candles[start:entry_index + 1]
    ]
    avg_range = sum(ranges) / len(ranges) if ranges else entry_price * 0.25
    min_risk_pct = 0.40 if ("OTM" in zone or "Breakout" in zone) else 0.28
    risk = max(entry_price * min_risk_pct, avg_range * 0.75)
    risk = min(risk, entry_price * 0.65)

    return {
        "sl": round(max(0.05, entry_price - risk), 2),
        "target1": round(entry_price + (risk * 1.5), 2),
        "target2": round(entry_price + (risk * 2.5), 2),
        "risk": round(risk, 2)
    }


def _resolve_exit(candles, entry_time, option_type, plan):
    start_index = 0
    for i, candle in enumerate(candles):
        if candle["time"] <= entry_time[:5]:
            start_index = i

    for candle in candles[start_index + 1:]:
        pnl = None

        if candle["low"] <= plan["sl"]:
            pnl = calculate_percent_change(plan["sl"], plan["entry"])
            return "SL Hit", plan["sl"], candle["time"], float(pnl)

        if candle["high"] >= plan["target2"]:
            pnl = calculate_percent_change(plan["target2"], plan["entry"])
            return "Target 2 Hit", plan["target2"], candle["time"], float(pnl)

        if candle["high"] >= plan["target1"]:
            pnl = calculate_percent_change(plan["target1"], plan["entry"])
            return "Target 1 Hit", plan["target1"], candle["time"], float(pnl)

        if abs(candle["delta"]) < DELTA_EXIT_ABS:
            pnl = calculate_percent_change(candle["close"], plan["entry"])
            return "Delta Exit", candle["close"], candle["time"], float(pnl)

    last = candles[-1]
    pnl = calculate_percent_change(last["close"], plan["entry"])
    return "Open", last["close"], last["time"], float(pnl)


def _detect_trade_entries(df):
    if df.empty:
        return []

    direction_by_time = _market_direction(df)
    signals = []

    for strike, part in df.groupby("strike"):
        part = part.sort_values("timestamp").reset_index(drop=True)

        for i in range(1, len(part)):
            curr = part.iloc[i]
            prev = part.iloc[i - 1]
            context = direction_by_time.get(curr["timestamp"], {"direction": "Neutral", "spot_3_change": 0})
            direction = context["direction"]

            if direction == "Neutral":
                continue

            atm = get_atm_strike(curr["spot"])

            for option_type in ("CE", "PE"):
                zone = _strike_zone(
                    option_type,
                    float(strike),
                    atm,
                    direction,
                    context["spot_3_change"]
                )

                if not zone:
                    continue

                metrics = _option_metrics(curr, prev, option_type)

                if metrics["price"] < MIN_ENTRY_LTP:
                    continue

                if metrics["buildup"] not in ("Long Build-up", "Short Covering"):
                    continue

                if metrics["price_change_pct"] < MIN_PRICE_CHANGE_PCT:
                    continue

                if abs(metrics["oi_change"]) < MIN_OI_CHANGE:
                    continue

                if abs(metrics["oi_change_pct"]) < MIN_OI_CHANGE_PCT:
                    continue

                if metrics["delta_abs"] < MIN_DELTA_ABS:
                    continue

                if metrics["delta_change"] < MIN_DELTA_CHANGE:
                    continue

                if metrics["gamma"] < MIN_GAMMA or metrics["gamma_change"] < MIN_GAMMA_CHANGE:
                    continue

                score, reason = _score_signal(metrics, zone, direction)
                if score < MIN_SIGNAL_SCORE:
                    continue

                candles = _build_candles(df, strike, option_type)
                entry_time = curr["timestamp"].strftime("%H:%M:%S")
                plan = _risk_plan(candles, metrics["price"], entry_time, zone)
                plan["entry"] = round(float(metrics["price"]), 2)
                outcome, exit_ltp, exit_time, pnl_pct = _resolve_exit(
                    candles,
                    entry_time,
                    option_type,
                    plan
                )

                signals.append({
                    "id": f"{curr['timestamp'].strftime('%H%M%S')}-{int(strike)}-{option_type}",
                    "time": entry_time,
                    "bucket": curr["timestamp"].floor(f"{INTERVAL_MINUTES}min").strftime("%H:%M"),
                    "direction": direction,
                    "zone": zone,
                    "setup": f"{option_type} {metrics['buildup']}",
                    "option": option_type,
                    "strike": int(strike),
                    "atm": int(atm),
                    "spot": round(float(curr["spot"]), 2),
                    "entry_ltp": plan["entry"],
                    "sl": plan["sl"],
                    "target1": plan["target1"],
                    "target2": plan["target2"],
                    "risk": plan["risk"],
                    "delta": round(float(metrics["delta"]), 4),
                    "delta_chg": float(metrics["delta_change"]),
                    "gamma": round(float(metrics["gamma"]), 6),
                    "gamma_chg": float(metrics["gamma_change"]),
                    "buildup": metrics["buildup"],
                    "oi_change": int(metrics["oi_change"]),
                    "oi_change_pct": float(metrics["oi_change_pct"]),
                    "price_change": round(float(metrics["price_change"]), 2),
                    "price_change_pct": float(metrics["price_change_pct"]),
                    "volume_change": int(metrics["volume_change"]),
                    "score": int(score),
                    "confidence": "High" if score >= 90 else "Medium",
                    "reason": reason,
                    "outcome": outcome,
                    "exit_ltp": round(float(exit_ltp), 2),
                    "exit_time": exit_time,
                    "pnl_pct": round(float(pnl_pct), 1)
                })

    signals = sorted(signals, key=lambda item: (-item["score"], item["time"]))

    # Avoid many repeated signals from the same strike/option burst.
    filtered = []
    seen = set()
    for signal in signals:
        key = (signal["strike"], signal["option"], signal["bucket"])
        if key in seen:
            continue
        seen.add(key)
        filtered.append(signal)

    return filtered[:40]


@router.get("/api/dashboard4")
def get_dashboard4_data():
    df = _fetch_session_df()

    if df.empty:
        return {"error": "No data found for selected trading session"}

    signals = _detect_trade_entries(df)
    latest = df.sort_values("timestamp").iloc[-1]
    spot = float(latest["spot"])

    closed = [s for s in signals if s["outcome"] != "Open"]
    wins = [s for s in closed if s["pnl_pct"] > 0]
    losses = [s for s in closed if s["pnl_pct"] < 0]
    net_pnl = round(sum(s["pnl_pct"] for s in closed), 1)

    selected = signals[0] if signals else None
    candles = []
    if selected:
        candles = _build_candles(df, selected["strike"], selected["option"])

    return {
        "data_date": get_data_date(),
        "spot": round(spot, 2),
        "atm": int(get_atm_strike(spot)),
        "signals": signals,
        "selected": selected,
        "candles": candles,
        "summary": {
            "total": len(signals),
            "closed": len(closed),
            "wins": len(wins),
            "losses": len(losses),
            "open": len(signals) - len(closed),
            "net_pnl_pct": net_pnl
        }
    }


@router.get("/api/dashboard4/candles")
def get_dashboard4_candles(strike: int, option: str = "CE"):
    df = _fetch_session_df()

    if df.empty:
        return {"error": "No data found for selected trading session"}

    option = option.upper()
    if option not in ("CE", "PE"):
        return {"error": "Invalid option type"}

    return {
        "strike": strike,
        "option": option,
        "candles": _build_candles(df, strike, option)
    }
