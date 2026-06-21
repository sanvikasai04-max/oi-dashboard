"""
Script 3: Options Flow Strength Analyser
═════════════════════════════════════════
Reads oi_2026_06_15.csv and produces a multi-layer strength report:

  LAYER 1 — Same-candle spike    : delta + gamma both spike in same timestamp
  LAYER 2 — Cross-candle trend   : delta + gamma + volume + price trending
                                   over N candles (user configurable)
  LAYER 3 — Cross-strike confirm : ATM strong → nearby strikes also strong?
  LAYER 4 — Opposite-side weak   : CE strong + PE weak = bullish confirmation
                                   PE strong + CE weak = bearish confirmation

All thresholds are computed at RUNTIME from the actual data (rolling percentile).
All % changes shown for delta, gamma, volume, price.
Data filtered to SESSION_START – SESSION_END window.

Usage : python 3_strength_analyser.py

Exit logic added for better option-point capture:

  1. Normal profit ladder
     Once the option moves in profit, the script protects part of the best move.
     Example:
       best move +70 pts -> try to keep at least +45 pts.

  2. Momentum entry room
     If option price itself is expanding strongly, the trade is treated as a
     momentum trade. Momentum trades are not trailed too tightly before +70 pts
     best move, because many good CE/PE moves first shake and then expand.

  3. Dynamic live strength exit
     After entry, every minute the script checks nearby strikes and builds a
     live score using:
       - option price percentage change
       - delta percentage change
       - gamma percentage change
       - volume percentage change
       - same-side build
       - opposite-side pressure

     For CE trades:
       CE_BUY build supports the trade.
       PE_SELL build also supports the CE trade.
       PE_BUY or CE_SELL warns that CE strength may be fading.

     For PE trades:
       PE_BUY build supports the trade.
       CE_SELL build also supports the PE trade.
       CE_BUY or PE_SELL warns that PE strength may be fading.

     Strong live score:
       keep trailing loose so bigger moves can continue.

     Weak live score:
       wait for confirmation bars, then tighten trailing to protect PNL.

     This is why a trade with big OI/price/delta build should not book only
     8-10 pts just because of one weak minute. The script waits for confirmed
     weakness and gives momentum entries enough room to capture larger points.

  4. Single active trade rule
     When ALLOW_OVERLAPPING_TRADES = False, the script allows only one active
     option trade at a time. If one entry is already running, all new entry
     signals are skipped until the first trade exits.
"""

import re
import sys
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import time as dtime

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

# ══════════════════════════════════════════════════════════════════════════════
# USER CONFIG
# ══════════════════════════════════════════════════════════════════════════════
CSV_PATH         = "oi_2024_12_31.csv"
ANALYSIS_DATE    = "2024-12-31"
SIDE             = "both"          # "ce" | "pe" | "both"
CROSS_CANDLES    = 5               # lookback window for cross-candle trend
STRIKES_NEARBY   = 2
ATM_RANGE_POINTS  = 500
STRIKE_STEP       = 50
STRENGTH_PCT     = 60              # percentile threshold for "strong" (runtime)
WEAK_PCT         = 40              # percentile threshold for "weak"  (runtime)

SESSION_START    = dtime(9, 20)    # filter: keep rows from this time onward
SESSION_END      = dtime(15, 30)   # filter: keep rows up to this time
OUT_CSV          = "strength_report.csv"
OUT_XLSX         = "strength_report.xlsx"
TOP_N = 20
ALLOW_OVERLAPPING_TRADES = False  # False = one active trade only; next entry after exit

# Exit rule:
# For CE/PE buy, exit when any 3 of Delta%, Gamma%, Volume%, Price% become negative.
EXIT_NEG_COUNT = 3
# EXIT CONFIG
MIN_HOLD_BARS = 20          # don't exit immediately after entry
EXIT_WEAK_BARS = 5          # need 3 continuous weak candles
TRAIL_DROP_PTS = 40         # exit if option falls 25 pts from best price
STOP_LOSS_PTS = 25          # fixed max loss from entry price
WEAK_EXIT_LOSS_PTS = 15     # weak exit only after this much loss, not while trade is green
MOMENTUM_MIN_HOLD_BARS = 45 # strong price-momentum entries get more room to develop

ENTRY_CUTOFF = dtime(15, 0)   # no new entries after 3 PM
FORCE_EXIT   = dtime(15, 0)   # force exit at/after 3 PM
TRAIL_ACTIVATE_PTS = 40     # trailing starts only after +30 pts profit
TRAIL_LOCK_PTS     = 30     # after activation, protect 20 pts profit

# Profit ladder for exits. Once best move reaches a tier, protect more profit.
# Format: (best_move_trigger, minimum_locked_profit, max_drop_from_best_price)
# Example: best +70 -> lock at least +45 and trail by 25 from the best price.
PROFIT_TRAIL_TIERS = [
    (100, 75, 25),
    (70, 45, 25),
    (40, 25, 20),
    (25, 10, 15),
]

# Price-momentum entries get wider trailing so fast CE/PE expansion is not
# booked too early. Example: if best move reaches +70, protect +45 but allow
# a 35 point pullback from best price.
MOMENTUM_PROFIT_TRAIL_TIERS = [
    (100, 75, 30),
    (70, 45, 35),
]

# Dynamic exit scoring:
# Every minute after entry, check nearby strikes for CE/PE build.
#
# For CE:
#   same-side build = CE buying strength
#   support build   = PE selling pressure
#   danger build    = PE buying or CE selling
#
# For PE:
#   same-side build = PE buying strength
#   support build   = CE selling pressure
#   danger build    = CE buying or PE selling
#
# Strong score means keep trailing loose to capture bigger move.
# Weak score means tighten trailing only after confirmation bars.
USE_DYNAMIC_STRENGTH_EXIT = True
DYNAMIC_EXIT_NEARBY_STRIKES = 2
STRONG_EXIT_SCORE = 8
WEAK_EXIT_SCORE = 3
DYNAMIC_WEAK_CONFIRM_BARS = 5
DYNAMIC_STRONG_CONFIRM_BARS = 2

MAX_PRICE_XPCT = 20

# Price momentum override:
# If option price itself expands strongly, allow that entry even when NIFTY is
# below/above 200 MA or the 200 MA is flat, as long as NIFTY is on the right
# side of EMA20. This catches breakout candles like 2024-12-31 10:52 CE.
USE_PRICE_MOMENTUM_OVERRIDE = True
PRICE_MOMENTUM_ENTRY_PCT = 10
ALLOW_PRICE_MOMENTUM_OVEREXTENDED = True

# NIFTY 200 MA trend filter:
#   If NIFTY close is below 200 MA -> block CE entries.
#   If NIFTY close is above 200 MA -> block PE entries.
USE_NIFTY_200MA_FILTER = True
NIFTY_1MIN_PATH = Path(__file__).resolve().parents[3] / "StrategyBuilder" / "nifty50database" / "nifty_5yr_1min.xlsx"
NIFTY_MA_PERIOD = 200

# Fast intraday direction filter:
# CE only when NIFTY is above both EMA20 and EMA50.
# PE only when NIFTY is below both EMA20 and EMA50.
# This avoids PE entries while price is still above 20/50 MA.
USE_FAST_EMA_DIRECTION_FILTER = True

# NIFTY chop filter from EMA slope/compression/crossing/range.
# If chop score >= threshold, skip both CE and PE entries.
USE_NIFTY_CHOP_FILTER = True
CHOP_SCORE_THRESHOLD = 3
BLOCK_IF_FLAT_200 = True
USE_SIMPLE_CHOP_HARD_BLOCK = True
FLAT_200_LOOKBACK = 30
FLAT_200_MAX_MOVE = 15
FLAT_20_LOOKBACK = 10
FLAT_20_MAX_MOVE = 8
FLAT_50_LOOKBACK = 15
FLAT_50_MAX_MOVE = 10
EMA20_50_GAP_MAX = 15
EMA50_200_GAP_MAX = 30
CLOSE_EMA20_GAP_MAX = 10
CROSS_LOOKBACK = 20
CROSS_COUNT_MIN = 3
AVG_RANGE_LOOKBACK = 20
AVG_RANGE_MAX = 10
# ══════════════════════════════════════════════════════════════════════════════

# ── ANSI ──────────────────────────────────────────────────────────────────────
def _c(t, code): return f"\033[{code}m{t}\033[0m"
def green(t):        return _c(t, "32")
def bright_green(t): return _c(t, "92")
def red(t):          return _c(t, "31")
def bright_red(t):   return _c(t, "91")
def yellow(t):       return _c(t, "33")
def orange(t):       return _c(t, "38;5;208")
def cyan(t):         return _c(t, "36")
def magenta(t):      return _c(t, "35")
def dim(t):          return _c(t, "2")
def bold(t):         return _c(t, "1")

def strip_ansi(s):
    return re.sub(r'\033\[[0-9;]*m', '', str(s))

def rjust(s, w):
    return ' ' * max(0, w - len(strip_ansi(s))) + s

def ljust(s, w):
    return s + ' ' * max(0, w - len(strip_ansi(s)))

def color_pct(val, extreme=20.0):
    if pd.isna(val): return dim("    n/a ")
    sign = "▲" if val > 0 else "▼" if val < 0 else " "
    txt  = f"{sign}{abs(val):6.2f}%"
    if val > extreme:    return bright_green(txt)
    elif val > 0:        return green(txt)
    elif val < -extreme: return bright_red(txt)
    elif val < 0:        return red(txt)
    return dim(txt)

def strength_bar(score, width=10):
    if score is None or pd.isna(score):
        return dim("[n/a]".ljust(width + 2))

    filled = int(round(float(score) / 100 * width))
    filled = max(0, min(width, filled))

    bar = "#" * filled + "-" * (width - filled)
    txt = f"[{bar}]"

    if score >= 75: return bright_green(txt)
    if score >= 50: return green(txt)
    if score >= 25: return yellow(txt)
    return red(txt)

def strength_label(score):
    if score >= 75: return bright_green("STRONG  ")
    if score >= 50: return green("MODERATE")
    if score >= 25: return yellow("WEAK    ")
    return red("VERY WK ")

def sep(w=130): print(dim("─" * w))
def header(title, w=130):
    print(bold("═" * w))
    print(bold(f"  {title}"))
    print(bold("═" * w))

def load_nifty_200ma():
    if not USE_NIFTY_200MA_FILTER:
        return None

    path = Path(NIFTY_1MIN_PATH)
    if not path.exists():
        print(yellow(f"  NIFTY 200 MA filter skipped: file not found: {path}"))
        return None

    nifty = pd.read_excel(path, usecols=["datetime", "high", "low", "close"])
    nifty["timestamp"] = pd.to_datetime(nifty["datetime"], dayfirst=True, errors="coerce")
    nifty["nifty_close"] = pd.to_numeric(nifty["close"], errors="coerce")
    nifty["nifty_high"] = pd.to_numeric(nifty["high"], errors="coerce")
    nifty["nifty_low"] = pd.to_numeric(nifty["low"], errors="coerce")
    nifty = nifty.dropna(subset=["timestamp", "nifty_close", "nifty_high", "nifty_low"]).sort_values("timestamp")

    nifty["ema20"] = nifty["nifty_close"].ewm(span=20, adjust=False).mean()
    nifty["ema50"] = nifty["nifty_close"].ewm(span=50, adjust=False).mean()
    nifty["nifty_ma200"] = nifty["nifty_close"].ewm(span=NIFTY_MA_PERIOD, adjust=False).mean()

    nifty["flat200"] = (nifty["nifty_ma200"] - nifty["nifty_ma200"].shift(FLAT_200_LOOKBACK)).abs() < FLAT_200_MAX_MOVE
    nifty["flat20"] = (nifty["ema20"] - nifty["ema20"].shift(FLAT_20_LOOKBACK)).abs() < FLAT_20_MAX_MOVE
    nifty["flat50"] = (nifty["ema50"] - nifty["ema50"].shift(FLAT_50_LOOKBACK)).abs() < FLAT_50_MAX_MOVE

    nifty["ma_compression"] = (
        ((nifty["ema20"] - nifty["ema50"]).abs() < EMA20_50_GAP_MAX) &
        ((nifty["ema50"] - nifty["nifty_ma200"]).abs() < EMA50_200_GAP_MAX) &
        ((nifty["nifty_close"] - nifty["ema20"]).abs() < CLOSE_EMA20_GAP_MAX)
    )

    ema_diff = nifty["ema20"] - nifty["ema50"]
    cross_now = (np.sign(ema_diff) != np.sign(ema_diff.shift(1))).astype(int)
    nifty["ema20_50_crosses"] = cross_now.rolling(CROSS_LOOKBACK, min_periods=1).sum()
    nifty["many_crosses"] = nifty["ema20_50_crosses"] >= CROSS_COUNT_MIN

    nifty["avg_range20"] = (nifty["nifty_high"] - nifty["nifty_low"]).rolling(AVG_RANGE_LOOKBACK, min_periods=1).mean()
    nifty["small_range"] = nifty["avg_range20"] < AVG_RANGE_MAX

    chop_cols = ["flat200", "flat50", "flat20", "ma_compression", "many_crosses", "small_range"]
    nifty["chop_score"] = nifty[chop_cols].astype(int).sum(axis=1)

    return nifty[[
        "timestamp", "nifty_close", "nifty_ma200", "ema20", "ema50",
        "flat200", "flat50", "flat20", "ma_compression", "many_crosses",
        "small_range", "ema20_50_crosses", "avg_range20", "chop_score",
    ]].dropna(subset=["nifty_ma200"])

def attach_nifty_200ma(full):
    nifty = load_nifty_200ma()
    if nifty is None or nifty.empty:
        full["nifty_close"] = np.nan
        full["nifty_ma200"] = np.nan
        full["chop_score"] = 0
        return full

    merged = pd.merge_asof(
        full.sort_values("timestamp"),
        nifty.sort_values("timestamp"),
        on="timestamp",
        direction="backward",
        tolerance=pd.Timedelta("1min"),
    )
    return merged.sort_values(["timestamp", "strike"]).reset_index(drop=True)

def passes_nifty_200ma_filter(row, side):
    if not USE_NIFTY_200MA_FILTER:
        return True, "OFF"

    close = row.get("nifty_close", np.nan)
    ma200 = row.get("nifty_ma200", np.nan)
    if pd.isna(close) or pd.isna(ma200):
        return True, "MA missing"

    if side == "ce" and close < ma200:
        return False, "CE blocked: NIFTY below 200 MA"
    if side == "pe" and close > ma200:
        return False, "PE blocked: NIFTY above 200 MA"
    return True, "OK"

def passes_fast_ema_direction_filter(row, side):
    if not USE_FAST_EMA_DIRECTION_FILTER:
        return True, "OFF"

    close = row.get("nifty_close", np.nan)
    ema20 = row.get("ema20", np.nan)
    ema50 = row.get("ema50", np.nan)
    if pd.isna(close) or pd.isna(ema20) or pd.isna(ema50):
        return True, "EMA missing"

    if side == "ce" and not (close >= ema20 and close >= ema50):
        return False, "CE blocked: NIFTY below EMA20/EMA50"
    if side == "pe" and not (close <= ema20 and close <= ema50):
        return False, "PE blocked: NIFTY above EMA20/EMA50"
    return True, "OK"

def passes_nifty_chop_filter(row):
    if not USE_NIFTY_CHOP_FILTER:
        return True, "OFF"

    score = row.get("chop_score", np.nan)
    if pd.isna(score):
        return True, "MA/chop missing"

    reasons = []
    for col, label in [
        ("flat200", "flat200"),
        ("flat50", "flat50"),
        ("flat20", "flat20"),
        ("ma_compression", "compression"),
        ("many_crosses", "crosses"),
        ("small_range", "small_range"),
    ]:
        if bool(row.get(col, False)):
            reasons.append(label)

    flat200 = bool(row.get("flat200", False))
    flat20 = bool(row.get("flat20", False))
    many_crosses = bool(row.get("many_crosses", False))
    compression = bool(row.get("ma_compression", False))
    flat50 = bool(row.get("flat50", False))

    if BLOCK_IF_FLAT_200 and flat200:
        return False, "FLAT_200_BLOCK " + ",".join(reasons)

    if USE_SIMPLE_CHOP_HARD_BLOCK and flat200 and flat20 and (many_crosses or compression or flat50):
        return False, "HARD_CHOP " + ",".join(reasons)

    if score < CHOP_SCORE_THRESHOLD:
        return True, f"score {int(score)}"

    return False, f"CHOP {int(score)}: " + ",".join(reasons)

def price_momentum_override(row, side, price_pct):
    if not USE_PRICE_MOMENTUM_OVERRIDE:
        return False, "OFF"

    close = row.get("nifty_close", np.nan)
    ema20 = row.get("ema20", np.nan)
    ema50 = row.get("ema50", np.nan)
    if pd.isna(close) or pd.isna(ema20) or pd.isna(ema50) or pd.isna(price_pct):
        return False, "missing"

    if price_pct < PRICE_MOMENTUM_ENTRY_PCT:
        return False, f"P%<{PRICE_MOMENTUM_ENTRY_PCT}"

    if side == "ce" and close >= ema20 and close >= ema50:
        return True, f"PRICE_MOMENTUM CE P%>={PRICE_MOMENTUM_ENTRY_PCT} NIFTY>=EMA20/50"
    if side == "pe" and close <= ema20 and close <= ema50:
        return True, f"PRICE_MOMENTUM PE P%>={PRICE_MOMENTUM_ENTRY_PCT} NIFTY<=EMA20/50"

    return False, "wrong side EMA20/50"

def live_side_build_counts(full, ts, strike):
    nearby = full[
        (full["timestamp"] == ts) &
        (full["strike"] >= strike - DYNAMIC_EXIT_NEARBY_STRIKES * STRIKE_STEP) &
        (full["strike"] <= strike + DYNAMIC_EXIT_NEARBY_STRIKES * STRIKE_STEP)
    ]

    if nearby.empty:
        return 0, 0, 0, 0

    ce_buy = int(((nearby["ce_d_pct"] > 3) & (nearby["ce_g_pct"] > 0) & (nearby["ce_v_pct"] > 30) & (nearby["ce_p_pct"] > 1)).sum())
    pe_sell = int(((nearby["pe_d_pct"] < 0) & (nearby["pe_v_pct"] > 30) & (nearby["pe_p_pct"] < -1)).sum())
    pe_buy = int(((nearby["pe_d_pct"] > 3) & (nearby["pe_g_pct"] > 0) & (nearby["pe_v_pct"] > 30) & (nearby["pe_p_pct"] > 1)).sum())
    ce_sell = int(((nearby["ce_d_pct"] < 0) & (nearby["ce_v_pct"] > 30) & (nearby["ce_p_pct"] < -1)).sum())

    return ce_buy, pe_sell, pe_buy, ce_sell

def live_exit_strength_score(full, row, strike, side):
    if not USE_DYNAMIC_STRENGTH_EXIT:
        return 0, "OFF"

    ts = row["timestamp"]
    ce_buy, pe_sell, pe_buy, ce_sell = live_side_build_counts(full, ts, strike)

    if side == "ce":
        same_build = ce_buy
        opp_support = pe_sell
        opposite_build = pe_buy + ce_sell
        d_pct = row.get("ce_d_pct", 0)
        g_pct = row.get("ce_g_pct", 0)
        v_pct = row.get("ce_v_pct", 0)
        p_pct = row.get("ce_p_pct", 0)
    else:
        same_build = pe_buy
        opp_support = ce_sell
        opposite_build = ce_buy + pe_sell
        d_pct = row.get("pe_d_pct", 0)
        g_pct = row.get("pe_g_pct", 0)
        v_pct = row.get("pe_v_pct", 0)
        p_pct = row.get("pe_p_pct", 0)

    own_score = 0
    own_score += 2 if d_pct > 3 else -1 if d_pct < 0 else 0
    own_score += 2 if g_pct > 0 else -1
    own_score += 2 if v_pct > 30 else -1 if v_pct < 0 else 0
    own_score += 2 if p_pct > 1 else -2 if p_pct < 0 else 0

    flow_score = same_build * 2 + opp_support * 2 - opposite_build * 2
    score = own_score + flow_score
    reason = f"LIVE={score} SAME={same_build} OPP_SUPPORT={opp_support} OPP_BUILD={opposite_build}"
    return score, reason

def dynamic_trailing_rule(best_move, live_score, momentum_entry):
    if best_move < 25:
        return None

    # Momentum entries need room. Do not start trailing them on small profit
    # unless the live score is strongly positive. This avoids booking 8-10 pts
    # before the later OI/price build creates the real move.
    if momentum_entry and best_move < 70 and live_score < STRONG_EXIT_SCORE:
        return None

    if live_score >= STRONG_EXIT_SCORE:
        if best_move >= 100:
            return 75, 40
        if best_move >= 70:
            return 45, 45
        if best_move >= 40:
            return 20, 50
        return 5, 40

    if live_score <= WEAK_EXIT_SCORE:
        if best_move >= 100:
            return 80, 25
        if best_move >= 70:
            return 50, 25
        if best_move >= 40:
            return 25, 20
        return 10, 15

    if momentum_entry:
        if best_move >= 100:
            return 75, 30
        if best_move >= 70:
            return 45, 35
        if best_move >= 40:
            return 25, 35
        return None

    if best_move >= 100:
        return 75, 25
    if best_move >= 70:
        return 45, 25
    if best_move >= 40:
        return 25, 20
    return 10, 15

def find_exit_after_entry(full, entry_ts, strike, side, entry_price, col_map, momentum_entry=False):
    cm = col_map[side]

    trade = full[
        (full["timestamp"] > entry_ts) &
        (full["strike"] == strike)
    ].copy().sort_values("timestamp").reset_index(drop=True)

    if trade.empty:
        return entry_ts, entry_price, 0, "No future data"

    best_price = entry_price
    weak_count = 0
    dynamic_weak_count = 0
    dynamic_strong_count = 0

    for i, r in trade.iterrows():
        price = r[cm["price"]]

        # Force exit at 3 PM
        if r["timestamp"].time() >= FORCE_EXIT:
            pnl = price - entry_price
            return r["timestamp"], price, pnl, "Exit: 3 PM force exit"
        
        price = r[cm["price"]]
        best_price = max(best_price, price)

        pnl_now = price - entry_price
        best_move = best_price - entry_price

        if pnl_now <= -STOP_LOSS_PTS:
            pnl = price - entry_price
            return r["timestamp"], price, pnl, "Exit: stop loss"

        min_hold_bars = MOMENTUM_MIN_HOLD_BARS if momentum_entry else MIN_HOLD_BARS

        # Do not exit too early
        if i < min_hold_bars:
            continue

        d_weak = r[f"{side}_d_pct"] < 0
        g_weak = r[f"{side}_g_pct"] < 0
        v_weak = r[f"{side}_v_pct"] < 0
        p_weak = r[f"{side}_p_pct"] < 0

        weak_now = sum([d_weak, g_weak, v_weak, p_weak]) >= 3

        if weak_now:
            weak_count += 1
        else:
            weak_count = 0

        live_score, live_reason = live_exit_strength_score(full, r, strike, side)
        if live_score <= WEAK_EXIT_SCORE:
            dynamic_weak_count += 1
        else:
            dynamic_weak_count = 0

        if live_score >= STRONG_EXIT_SCORE:
            dynamic_strong_count += 1
        else:
            dynamic_strong_count = 0

        confirmed_live_score = 5
        if dynamic_strong_count >= DYNAMIC_STRONG_CONFIRM_BARS:
            confirmed_live_score = live_score
        elif dynamic_weak_count >= DYNAMIC_WEAK_CONFIRM_BARS:
            confirmed_live_score = live_score

        dynamic_rule = dynamic_trailing_rule(best_move, confirmed_live_score, momentum_entry)

        if dynamic_rule:
            lock_pts, drop_pts = dynamic_rule
            trail_sl = max(entry_price + lock_pts, best_price - drop_pts)

            if price <= trail_sl:
                pnl = price - entry_price
                return r["timestamp"], price, pnl, (
                    f"Exit: dynamic trail +{lock_pts} {live_reason} "
                    f"W{dynamic_weak_count} S{dynamic_strong_count}"
                )

        # Weakness exit is for failed trades only. Do not kill a green trade
        # just because Greeks cool off before the option makes its larger move.
        if weak_count >= EXIT_WEAK_BARS and best_move < 25 and pnl_now <= -WEAK_EXIT_LOSS_PTS:
            pnl = price - entry_price
            return r["timestamp"], price, pnl, "Exit: weak failed trade"

    last = trade.iloc[-1]
    exit_price = last[cm["price"]]
    pnl = exit_price - entry_price
    return last["timestamp"], exit_price, pnl, "Exit: session end"


def compute_strike_best_move(full, entry_ts, strike, side, entry_price, col_map):
    """
    Best move for the SAME STRIKE only.
    Checks future candles after entry for the same strike and same side price.
    """
    cm = col_map[side]
    future = full[
        (full["timestamp"] > entry_ts) &
        (full["strike"] == strike)
    ].copy().sort_values("timestamp")

    if future.empty:
        return 0.0, entry_ts, entry_price

    best_idx = future[cm["price"]].idxmax()
    best_row = future.loc[best_idx]
    best_price = float(best_row[cm["price"]])
    best_move = best_price - float(entry_price)

    return round(best_move, 2), best_row["timestamp"], round(best_price, 2)

def get_flow_confirm(full, ts, strike, side):
    """
    Captures moves like 28/29 Oct:
    CE price+volume buying + PE price down with volume up = bullish confirmation.
    PE price+volume buying + CE price down with volume up = bearish confirmation.
    Gamma is kept low weight because both sides gamma can rise.
    """
    nearby = full[
        (full["timestamp"] == ts) &
        (full["strike"] >= strike - STRIKES_NEARBY * STRIKE_STEP) &
        (full["strike"] <= strike + STRIKES_NEARBY * STRIKE_STEP)
    ].copy()

    if nearby.empty:
        return 0, 0, 0, "NO_NEARBY"

    ce_buy = 0
    pe_sell = 0
    pe_buy = 0
    ce_sell = 0

    for _, r in nearby.iterrows():
        # CE buying strength
        if r["ce_d_pct"] > 3 and r["ce_v_pct"] > 30 and r["ce_p_pct"] > 1:
            ce_buy += 1

        # PE selling / bullish opposite confirmation
        if r["pe_d_pct"] < 0 and r["pe_v_pct"] > 30 and r["pe_p_pct"] < -1:
            pe_sell += 1

        # PE buying strength
        if r["pe_d_pct"] > 3 and r["pe_v_pct"] > 30 and r["pe_p_pct"] > 1:
            pe_buy += 1

        # CE selling / bearish opposite confirmation
        if r["ce_d_pct"] < 0 and r["ce_v_pct"] > 30 and r["ce_p_pct"] < -1:
            ce_sell += 1

    if side == "ce":
        flow_score = ce_buy * 2 + pe_sell * 2
        reason = f"CE_BUY={ce_buy} PE_SELL={pe_sell}"
        return flow_score, ce_buy, pe_sell, reason

    flow_score = pe_buy * 2 + ce_sell * 2
    reason = f"PE_BUY={pe_buy} CE_SELL={ce_sell}"
    return flow_score, pe_buy, ce_sell, reason
# ══════════════════════════════════════════════════════════════════════════════
# CORE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════
def pct_change_col(series):
    return (series.pct_change() * 100).round(2)

def rolling_pct_rank(series, window=20):
    return series.rolling(window, min_periods=1).apply(
        lambda x: (x[-1] > x[:-1]).mean() * 100 if len(x) > 1 else 50.0,
        raw=True
    )

def compute_strength_score(delta_rank, gamma_rank, volume_rank, price_rank):
    return (
        0.30 * delta_rank +
        0.30 * gamma_rank +
        0.25 * volume_rank +
        0.15 * price_rank
    ).round(1)

def cross_candle_trend(series, n):
    def slope_sign(x):
        if len(x) < 2: return 0
        xs = np.arange(len(x))
        slope = np.polyfit(xs, x, 1)[0]
        if slope > 0:  return 1
        if slope < 0:  return -1
        return 0
    return series.rolling(n, min_periods=2).apply(slope_sign, raw=True)

def cross_candle_pct(series, n):
    return ((series - series.shift(n)) / series.shift(n).abs() * 100).round(2)

def safe_float(x):
    try:
        v = float(x)
        return None if np.isnan(v) else v
    except Exception:
        return None

# ══════════════════════════════════════════════════════════════════════════════
# XLSX EXPORT  — mimics console colours as cell fills / fonts
# ══════════════════════════════════════════════════════════════════════════════
def _export_xlsx(full, layer1_rows, layer2_rows, opp_rows, sides, col_map, save_cols, timestamps):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side as XLSide
    from openpyxl.utils import get_column_letter

    # ── Palette ───────────────────────────────────────────────────────────────
    HDR_BG      = PatternFill("solid", start_color="1F4E79")
    HDR_FONT    = Font(name="Consolas", bold=True, color="FFFFFF", size=10)
    BODY_FONT   = Font(name="Consolas", size=9)
    BOLD_FONT   = Font(name="Consolas", size=9, bold=True)
    ALT_FILL    = PatternFill("solid", start_color="1A1A2E")   # dark alt row
    DARK_FILL   = PatternFill("solid", start_color="16213E")   # base dark
    BULL_FILL   = PatternFill("solid", start_color="1A3A1A")   # dark green
    BEAR_FILL   = PatternFill("solid", start_color="3A1A1A")   # dark red
    SPIKE_FILL  = PatternFill("solid", start_color="2A2A0A")   # dark yellow

    # text colours
    C_BRIGHT_GREEN = "92FF92"
    C_GREEN        = "00CC00"
    C_BRIGHT_RED   = "FF9292"
    C_RED          = "FF4444"
    C_YELLOW       = "FFFF00"
    C_CYAN         = "00FFFF"
    C_DIM          = "888888"
    C_WHITE        = "FFFFFF"

    thin = XLSide(style="thin", color="333355")
    bdr  = Border(left=thin, right=thin, top=thin, bottom=thin)

    def hfont(color=C_WHITE): return Font(name="Consolas", bold=True,  color=color, size=9)
    def bfont(color=C_WHITE, bold=False): return Font(name="Consolas", bold=bold, color=color, size=9)

    def pct_color(val, extreme=20.0):
        """Return (text_str, hex_color) for a pct value."""
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return "n/a", C_DIM
        sign = "▲" if val > 0 else "▼" if val < 0 else " "
        txt  = f"{sign}{abs(val):.2f}%"
        if val > extreme:    clr = C_BRIGHT_GREEN
        elif val > 0:        clr = C_GREEN
        elif val < -extreme: clr = C_BRIGHT_RED
        elif val < 0:        clr = C_RED
        else:                clr = C_DIM
        return txt, clr

    def score_color(score):
        if score >= 75: return C_BRIGHT_GREEN
        if score >= 50: return C_GREEN
        if score >= 25: return C_YELLOW
        return C_RED

    def score_label(score):
        if score >= 75: return "STRONG"
        if score >= 50: return "MODERATE"
        if score >= 25: return "WEAK"
        return "VERY WK"

    def write_cell(ws, row, col, value, fg=C_WHITE, bg=None, bold=False, align="center"):
        cell = ws.cell(row=row, column=col, value=value)
        cell.font      = Font(name="Consolas", color=fg, bold=bold, size=9)
        cell.alignment = Alignment(horizontal=align, vertical="center")
        cell.border    = bdr
        if bg:
            cell.fill = PatternFill("solid", start_color=bg)
        return cell

    def style_header_row(ws, cols, row=1):
        for ci, col_name in enumerate(cols, 1):
            cell = ws.cell(row=row, column=ci, value=col_name)
            cell.font      = HDR_FONT
            cell.fill      = HDR_BG
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border    = bdr
        ws.row_dimensions[row].height = 18

    def autofit(ws, extra=3, max_w=35):
        for col_cells in ws.columns:
            best = max((len(str(c.value or "")) for c in col_cells), default=8)
            ws.column_dimensions[get_column_letter(col_cells[0].column)].width = min(best + extra, max_w)

    wb = Workbook()

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 1 — LAYER 1  Same-Candle Spikes
    # ══════════════════════════════════════════════════════════════════════════
    ws1 = wb.active
    ws1.title       = "L1 Same-Candle Spikes"
    ws1.sheet_view.showGridLines = False
    ws1.sheet_properties.tabColor = "FFEB9C"

    l1_hdr = ["TIMESTAMP","STRIKE","SPOT","SIDE","SCORE","STRENGTH",
              "DELTA","DELTA_%","GAMMA","GAMMA_%",
              "VOLUME","VOLUME_%","PRICE","PRICE_%","IV"]
    style_header_row(ws1, l1_hdr)

    for ri, (ts, stk, spot, side, score, dv, dp, gv, gp, vv, vp, pv, pp, iv) in enumerate(layer1_rows, 2):
        row_bg = "1A3A1A" if side == "ce" else "3A1A1A"
        sc     = score_color(score)
        sl     = score_label(score)
        dp_t, dp_c = pct_color(safe_float(dp))
        gp_t, gp_c = pct_color(safe_float(gp))
        vp_t, vp_c = pct_color(safe_float(vp), 50)
        pp_t, pp_c = pct_color(safe_float(pp))

        write_cell(ws1, ri, 1,  str(ts)[:19],             C_DIM,          row_bg)
        write_cell(ws1, ri, 2,  round(stk,1),              C_CYAN,         row_bg)
        write_cell(ws1, ri, 3,  round(spot,2),             C_CYAN,         row_bg)
        write_cell(ws1, ri, 4,  side.upper(),              C_BRIGHT_GREEN if side=="ce" else C_BRIGHT_RED, row_bg, bold=True)
        write_cell(ws1, ri, 5,  round(score,1),            sc,             row_bg, bold=True)
        write_cell(ws1, ri, 6,  sl,                        sc,             row_bg)
        write_cell(ws1, ri, 7,  round(float(dv),4) if safe_float(dv) is not None else None, C_WHITE, row_bg)
        write_cell(ws1, ri, 8,  dp_t,                      dp_c,           row_bg)
        write_cell(ws1, ri, 9,  round(float(gv),6) if safe_float(gv) is not None else None, C_WHITE, row_bg)
        write_cell(ws1, ri, 10, gp_t,                      gp_c,           row_bg)
        write_cell(ws1, ri, 11, int(vv) if safe_float(vv) is not None else None, C_DIM, row_bg)
        write_cell(ws1, ri, 12, vp_t,                      vp_c,           row_bg)
        write_cell(ws1, ri, 13, round(float(pv),2) if safe_float(pv) is not None else None, C_WHITE, row_bg)
        write_cell(ws1, ri, 14, pp_t,                      pp_c,           row_bg)
        write_cell(ws1, ri, 15, round(float(iv),2) if safe_float(iv) is not None else None, C_DIM, row_bg)

    ws1.freeze_panes = "A2"
    autofit(ws1)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 2 — LAYER 2  Cross-Candle Trend
    # ══════════════════════════════════════════════════════════════════════════
    ws2 = wb.create_sheet("L2 Cross-Candle Trend")
    ws2.sheet_view.showGridLines = False
    ws2.sheet_properties.tabColor = "00BFFF"

    l2_hdr = ["TIMESTAMP","STRIKE","SPOT","SIDE","DIRECTION","SCORE",
              f"DELTA_%_{CROSS_CANDLES}c", f"GAMMA_%_{CROSS_CANDLES}c",
              f"VOLUME_%_{CROSS_CANDLES}c", f"PRICE_%_{CROSS_CANDLES}c"]
    style_header_row(ws2, l2_hdr)

    for ri, (ts, stk, spot, side, direction, score, d_xp, g_xp, v_xp, p_xp) in enumerate(layer2_rows, 2):
        is_bull = direction == "BULLISH"
        row_bg  = "1A3A1A" if is_bull else "3A1A1A"
        sc      = score_color(score)
        dir_c   = C_BRIGHT_GREEN if is_bull else C_BRIGHT_RED
        dxt, dxc = pct_color(safe_float(d_xp), 30)
        gxt, gxc = pct_color(safe_float(g_xp), 30)
        vxt, vxc = pct_color(safe_float(v_xp), 50)
        pxt, pxc = pct_color(safe_float(p_xp), 20)

        write_cell(ws2, ri, 1,  str(ts)[:19],   C_DIM,  row_bg)
        write_cell(ws2, ri, 2,  round(stk,1),   C_CYAN, row_bg)
        write_cell(ws2, ri, 3,  round(spot,2),  C_CYAN, row_bg)
        write_cell(ws2, ri, 4,  side.upper(),   C_BRIGHT_GREEN if side=="CE" else C_BRIGHT_RED, row_bg, bold=True)
        write_cell(ws2, ri, 5,  direction,      dir_c,  row_bg, bold=True)
        write_cell(ws2, ri, 6,  round(score,1), sc,     row_bg, bold=True)
        write_cell(ws2, ri, 7,  dxt,            dxc,    row_bg)
        write_cell(ws2, ri, 8,  gxt,            gxc,    row_bg)
        write_cell(ws2, ri, 9,  vxt,            vxc,    row_bg)
        write_cell(ws2, ri, 10, pxt,            pxc,    row_bg)

    ws2.freeze_panes = "A2"
    autofit(ws2)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 3 — LAYER 3  Cross-Strike Confirmation
    # ══════════════════════════════════════════════════════════════════════════
    ws3 = wb.create_sheet("L3 Cross-Strike Confirm")
    ws3.sheet_view.showGridLines = False
    ws3.sheet_properties.tabColor = "9900FF"

    offsets   = [i for i in range(-STRIKES_NEARBY, STRIKES_NEARBY+1) if i != 0]
    l3_hdr    = ["TIMESTAMP","ATM","SPOT","SIDE","ATM SCORE"] + \
                [f"ATM{'+' if i>0 else ''}{i}" for i in offsets]
    style_header_row(ws3, l3_hdr)

    all_strikes_local = sorted(full["strike"].unique())

    ri = 2
    for ts in timestamps:
        ts_data = full[full["timestamp"] == ts]
        spot    = ts_data["spot"].iloc[0]
        atm_idx = (ts_data["strike"] - spot).abs().idxmin()
        atm_stk = ts_data.loc[atm_idx, "strike"]
        try:
            atm_pos = all_strikes_local.index(atm_stk)
        except ValueError:
            continue

        for side in sides:
            atm_score_s = ts_data.loc[ts_data["strike"]==atm_stk, f"{side}_score"]
            if atm_score_s.empty: continue
            atm_score = atm_score_s.iloc[0]
            if atm_score < STRENGTH_PCT: continue

            row_bg = "1A1A3A"
            write_cell(ws3, ri, 1, str(ts)[:19],  C_DIM,  row_bg)
            write_cell(ws3, ri, 2, round(atm_stk,1), C_CYAN, row_bg)
            write_cell(ws3, ri, 3, round(spot,2),    C_CYAN, row_bg)
            write_cell(ws3, ri, 4, side.upper(), C_BRIGHT_GREEN if side=="ce" else C_BRIGHT_RED, row_bg, bold=True)
            write_cell(ws3, ri, 5, round(atm_score,1), score_color(atm_score), row_bg, bold=True)

            for ci, offset in enumerate(offsets, 6):
                ni = atm_pos + offset
                if 0 <= ni < len(all_strikes_local):
                    nstk = all_strikes_local[ni]
                    row  = ts_data[ts_data["strike"]==nstk]
                    sc   = row[f"{side}_score"].iloc[0] if not row.empty else None
                else:
                    sc = None
                if sc is not None:
                    write_cell(ws3, ri, ci, round(sc,1), score_color(sc), row_bg)
                else:
                    write_cell(ws3, ri, ci, "n/a", C_DIM, row_bg)
            ri += 1

    ws3.freeze_panes = "A2"
    autofit(ws3)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 4 — LAYER 4  Opposite-Side Weak Confirmation
    # ══════════════════════════════════════════════════════════════════════════
    ws4 = wb.create_sheet("L4 Opp-Side Confirm")
    ws4.sheet_view.showGridLines = False
    ws4.sheet_properties.tabColor = "FF4500"

    l4_hdr = ["TIMESTAMP","STRIKE","SPOT","SIGNAL",
              "CE SCORE","PE SCORE",
              "CE D%","CE G%","PE D%","PE G%","CONFIDENCE"]
    style_header_row(ws4, l4_hdr)

    for ri, (ts, stk, spot, signal, ce_sc, pe_sc, ce_dp, ce_gp, pe_dp, pe_gp, conf) in enumerate(opp_rows, 2):
        sig_clean = strip_ansi(signal)
        is_bull   = "BULL" in sig_clean
        row_bg    = "1A3A1A" if is_bull else "3A1A1A"
        sig_c     = C_BRIGHT_GREEN if is_bull else C_BRIGHT_RED
        sig_txt   = "▲ BULLISH CONFIRM" if is_bull else "▼ BEARISH CONFIRM"

        ce_dp_t, ce_dp_c = pct_color(safe_float(ce_dp))
        ce_gp_t, ce_gp_c = pct_color(safe_float(ce_gp))
        pe_dp_t, pe_dp_c = pct_color(safe_float(pe_dp))
        pe_gp_t, pe_gp_c = pct_color(safe_float(pe_gp))

        write_cell(ws4, ri, 1,  str(ts)[:19],       C_DIM,             row_bg)
        write_cell(ws4, ri, 2,  round(stk,1),        C_CYAN,            row_bg)
        write_cell(ws4, ri, 3,  round(spot,2),       C_CYAN,            row_bg)
        write_cell(ws4, ri, 4,  sig_txt,             sig_c,             row_bg, bold=True)
        write_cell(ws4, ri, 5,  round(ce_sc,1),      score_color(ce_sc),row_bg, bold=True)
        write_cell(ws4, ri, 6,  round(pe_sc,1),      score_color(pe_sc),row_bg, bold=True)
        write_cell(ws4, ri, 7,  ce_dp_t,             ce_dp_c,           row_bg)
        write_cell(ws4, ri, 8,  ce_gp_t,             ce_gp_c,           row_bg)
        write_cell(ws4, ri, 9,  pe_dp_t,             pe_dp_c,           row_bg)
        write_cell(ws4, ri, 10, pe_gp_t,             pe_gp_c,           row_bg)
        write_cell(ws4, ri, 11, round(conf,1),        score_color(min(conf,100)), row_bg, bold=True)

    ws4.freeze_panes = "A2"
    autofit(ws4)

    # ══════════════════════════════════════════════════════════════════════════
    # SHEET 5 — Full Data
    # ══════════════════════════════════════════════════════════════════════════
    ws_fd = wb.create_sheet("Full Data")
    ws_fd.sheet_view.showGridLines = False
    ws_fd.sheet_properties.tabColor = "444444"

    existing = [c for c in save_cols if c in full.columns]
    style_header_row(ws_fd, existing)

    for ri2, row in enumerate(full[existing].itertuples(index=False), 2):
        bg = "1A1A2E" if ri2 % 2 == 0 else "16213E"
        for ci2, val in enumerate(row, 1):
            if hasattr(val, "isoformat"):
                v = val.isoformat()
            elif isinstance(val, (bool, np.bool_)):
                v = str(val)
            elif isinstance(val, float) and np.isnan(val):
                v = None
            else:
                v = val
            write_cell(ws_fd, ri2, ci2, v, C_WHITE, bg)

    ws_fd.freeze_panes = "A2"
    autofit(ws_fd)

    # ══════════════════════════════════════════════════════════════════════════
    # Set dark background for all sheets' tab area via sheet background
    # ══════════════════════════════════════════════════════════════════════════
    wb.save(OUT_XLSX)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
def main():
    csv = Path(CSV_PATH)
    if not csv.exists():
        raise FileNotFoundError(f"CSV not found: {CSV_PATH}\nRun 1_db_to_csv.py first.")

    print(bold(cyan(f"\n  Loading {CSV_PATH} …")))
    df = pd.read_csv(CSV_PATH, parse_dates=["timestamp"])
    print("CSV date range:", df["timestamp"].min(), "to", df["timestamp"].max())


    # Keep only selected date from the CSV
    # Keep only selected date from the CSV
    df = df[df["timestamp"].dt.date == pd.to_datetime(ANALYSIS_DATE).date()].copy()
    df.reset_index(drop=True, inplace=True)

    # Stop script clearly if selected date is not available in CSV
    if df.empty:
        print(red(f"No rows found for ANALYSIS_DATE = {ANALYSIS_DATE}"))
        print(yellow("Use one date from Available dates printed above."))
        return

    df.sort_values(["timestamp", "strike"], inplace=True)
    df.reset_index(drop=True, inplace=True)

    # ── Session time filter ───────────────────────────────────────────────────
    before = len(df)

    df = df[df["timestamp"].dt.time.between(SESSION_START, SESSION_END)].copy()
    df.reset_index(drop=True, inplace=True)

    # Keep only ATM ±100 points for each timestamp
    df["atm_strike"] = (df["spot"] / STRIKE_STEP).round() * STRIKE_STEP

    df = df[
        (df["strike"] >= df["atm_strike"] - ATM_RANGE_POINTS) &
        (df["strike"] <= df["atm_strike"] + ATM_RANGE_POINTS)
    ].copy()

    df.drop(columns=["atm_strike"], inplace=True)
    df.reset_index(drop=True, inplace=True)
    after  = len(df)
    print(f"  {dim('Time filter:')} {SESSION_START.strftime('%H:%M')} – {SESSION_END.strftime('%H:%M')}  "
          f"{dim('Rows:')} {before:,} → {bright_green(str(after))}")

    sides   = ["ce","pe"] if SIDE == "both" else [SIDE]
    col_map = {
        "ce": {"delta":"call_delta","gamma":"call_gamma",
               "volume":"call_volume","price":"call_price","iv":"call_iv"},
        "pe": {"delta":"put_delta", "gamma":"put_gamma",
               "volume":"put_volume","price":"put_price","iv":"put_iv"},
    }

    print(f"  {dim('Timestamps:')} {df['timestamp'].nunique()}  "
          f"{dim('Strikes:')} {df['strike'].nunique()}  "
          f"{dim('Sides:')} {SIDE.upper()}  "
          f"{dim('X-candle window:')} {CROSS_CANDLES}  "
          f"{dim('Nearby strikes:')} ±{STRIKES_NEARBY}\n")

    # ── Per-strike feature engineering ───────────────────────────────────────
    all_strikes = sorted(df["strike"].unique())
    records     = []

    for strike in all_strikes:
        sdf = df[df["strike"] == strike].copy().sort_values("timestamp").reset_index(drop=True)
        if len(sdf) < 3:
            continue

        for side in sides:
            cm = col_map[side]
            d  = sdf[cm["delta"]].copy()
            g  = sdf[cm["gamma"]].copy()
            v  = sdf[cm["volume"]].copy()
            p  = sdf[cm["price"]].copy()

            sdf[f"{side}_d_pct"]   = pct_change_col(d)
            sdf[f"{side}_g_pct"]   = pct_change_col(g)
            sdf[f"{side}_v_pct"]   = pct_change_col(v)
            sdf[f"{side}_p_pct"]   = pct_change_col(p)

            sdf[f"{side}_d_xpct"]  = cross_candle_pct(d, CROSS_CANDLES)
            sdf[f"{side}_g_xpct"]  = cross_candle_pct(g, CROSS_CANDLES)
            sdf[f"{side}_v_xpct"]  = cross_candle_pct(v, CROSS_CANDLES)
            sdf[f"{side}_p_xpct"]  = cross_candle_pct(p, CROSS_CANDLES)
            sdf[f"{side}_overextended"] = sdf[f"{side}_p_xpct"] > MAX_PRICE_XPCT

            sdf[f"{side}_d_trend"] = cross_candle_trend(d, CROSS_CANDLES)
            sdf[f"{side}_g_trend"] = cross_candle_trend(g, CROSS_CANDLES)
            sdf[f"{side}_v_trend"] = cross_candle_trend(v, CROSS_CANDLES)
            sdf[f"{side}_p_trend"] = cross_candle_trend(p, CROSS_CANDLES)

            sdf[f"{side}_d_rank"]  = rolling_pct_rank(d)
            sdf[f"{side}_g_rank"]  = rolling_pct_rank(g)
            sdf[f"{side}_v_rank"]  = rolling_pct_rank(v)
            sdf[f"{side}_p_rank"]  = rolling_pct_rank(p)

            sdf[f"{side}_score"]   = compute_strength_score(
                sdf[f"{side}_d_rank"], sdf[f"{side}_g_rank"],
                sdf[f"{side}_v_rank"], sdf[f"{side}_p_rank"]
            )

            sdf[f"{side}_same_spike"] = (
                (sdf[f"{side}_d_rank"] >= STRENGTH_PCT) &
                (sdf[f"{side}_g_rank"] >= STRENGTH_PCT)
            )
            sdf[f"{side}_cross_bull"] = (
                (sdf[f"{side}_d_trend"] == 1) &
                (sdf[f"{side}_g_trend"] == 1) &
                (sdf[f"{side}_v_trend"] == 1)
            )
            sdf[f"{side}_cross_bear"] = (
                (sdf[f"{side}_d_trend"] == -1) &
                (sdf[f"{side}_g_trend"] == -1) &
                (sdf[f"{side}_v_trend"] == -1)
            )

        records.append(sdf)

    full       = pd.concat(records, ignore_index=True).sort_values(["timestamp","strike"])
    full       = attach_nifty_200ma(full)
    timestamps = sorted(full["timestamp"].unique())

    W  = 148   # console width — wide enough for all columns
    W3 = W + STRIKES_NEARBY * 14

    # ══════════════════════════════════════════════════════════════════════════
    # LAYER 1 — SAME-CANDLE SPIKE REPORT
    # ══════════════════════════════════════════════════════════════════════════
    header("LAYER 1 — SAME-CANDLE SPIKE  (Delta ∧ Gamma both high simultaneously)", W)
    print(f"  {dim('Threshold: runtime percentile ≥')} {bold(str(STRENGTH_PCT))}th\n")

    h1 = (f"  {'TIMESTAMP':<19}  {'STRIKE':>8}  {'SPOT':>8}  {'SIDE':>4}  "
          f"{'SCORE':>5}  {'STRENGTH':>18}  "
          f"{'DELTA':>10} {'D CHG%':>9}  {'GAMMA':>10} {'G CHG%':>9}  "
          f"{'VOLUME':>10} {'V%':>9}  {'PRICE':>8} {'P%':>9}  {'IV':>7}")
    print(bold(h1))
    sep(W)
    
    
    layer1_rows = []
    for side in sides:
        sub = full[full[f"{side}_same_spike"]].copy()
        for _, r in sub.iterrows():
            layer1_rows.append((r["timestamp"], r["strike"], r["spot"], side,
                                r[f"{side}_score"],
                                r[col_map[side]["delta"]], r[f"{side}_d_pct"],
                                r[col_map[side]["gamma"]], r[f"{side}_g_pct"],
                                r[col_map[side]["volume"]],r[f"{side}_v_pct"],
                                r[col_map[side]["price"]], r[f"{side}_p_pct"],
                                r[col_map[side]["iv"]]))

    # Same timestamp → all CE first → all PE next
    layer1_rows.sort(key=lambda x: (x[0], 0 if x[3] == "ce" else 1, x[1]))

    for ts, stk, spot, side, score, dv, dp, gv, gp, vv, vp, pv, pp, iv in layer1_rows:
        sc     = f"{score:5.1f}"
        bar    = strength_bar(score)
        lbl    = strength_label(score)
        side_c = bright_green("CE") if side == "ce" else bright_red("PE")
        dv_d   = dv
        gv_d   = gv
        print(
            f"  {dim(str(ts)[:19])}  "
            f"{cyan(f'{stk:>8.1f}')}  {cyan(f'{spot:>8.2f}')}  {side_c}  "
            f"{bold(sc)}  {bar} {lbl}  "
            f"{rjust(dim(f'{dv_d:>10.4f}'), 10)} {rjust(color_pct(dp), 9)}  "
            f"{rjust(dim(f'{gv_d:>10.6f}'), 10)} {rjust(color_pct(gp), 9)}  "
            f"{rjust(dim(f'{vv:>10,.0f}'), 10)} {rjust(color_pct(vp, 50), 9)}  "
            f"{dim(f'{pv:>8.2f}')} {rjust(color_pct(pp), 9)}  "
            f"{dim(f'{iv:>7.2f}%')}"
        )

    if not layer1_rows:
        print(f"  {dim('No same-candle spikes found.')}")
    sep(W)

    # TOP ENTRIES TABLE — best entry candles from Layer 1 data
    # Logic: delta up + gamma up + volume up + price up
    # Extra rule: one best row per timestamp, so duplicate same-time entries are removed
    # ══════════════════════════════════════════════════════════════════════════
    header("TOP ENTRIES — Delta + Gamma + Volume + Price increasing", W)
    pe_total = 0
    pe_gamma_reject = 0
    pe_overextended_reject = 0
    pe_flow_reject = 0
    pe_strength_reject = 0
    pe_pass = 0
    ce_ma_reject = 0
    pe_ma_reject = 0
    ma_missing_count = 0
    ce_fast_ema_reject = 0
    pe_fast_ema_reject = 0
    fast_ema_missing_count = 0
    chop_reject = 0
    chop_missing_count = 0
    momentum_override_count = 0
    top_rows = []

    for row in layer1_rows:
        ts, stk, spot, side, score, dv, dp, gv, gp, vv, vp, pv, pp, iv = row

        if side == "pe":
            pe_total += 1

        r = full[
            (full["timestamp"] == ts) &
            (full["strike"] == stk)
        ].iloc[0]

        if ts.time() >= ENTRY_CUTOFF:
            continue

        momentum_ok, momentum_reason = price_momentum_override(r, side, pp)

        ma_ok, ma_reason = passes_nifty_200ma_filter(r, side)
        if ma_reason == "MA missing":
            ma_missing_count += 1
        if not ma_ok and not momentum_ok:
            if side == "ce":
                ce_ma_reject += 1
            else:
                pe_ma_reject += 1
            continue

        fast_ema_ok, fast_ema_reason = passes_fast_ema_direction_filter(r, side)
        if fast_ema_reason == "EMA missing":
            fast_ema_missing_count += 1
        if not fast_ema_ok:
            if side == "ce":
                ce_fast_ema_reject += 1
            else:
                pe_fast_ema_reject += 1
            continue

        chop_ok, chop_reason = passes_nifty_chop_filter(r)
        if chop_reason == "MA/chop missing":
            chop_missing_count += 1
        if not chop_ok and not momentum_ok:
            chop_reject += 1
            continue

        if momentum_ok and (not ma_ok or not chop_ok):
            momentum_override_count += 1

        # reject already extended candles
        if r[f"{side}_overextended"] and not (ALLOW_PRICE_MOMENTUM_OVEREXTENDED and momentum_ok):
            if side == "pe":
                pe_overextended_reject += 1
            continue

        # avoid gamma-negative entries
        if gp <= 0:
            if side == "pe":
                pe_gamma_reject += 1
            continue

        flow_score, same_side_count, opp_side_count, flow_reason = get_flow_confirm(
            full, ts, stk, side
        )

        if side == "ce":
            delta_ok = dp > 3
        else:
            delta_ok = dp > 3

        price_ok = pp > 1
        volume_ok = vp > 30
        flow_ok = flow_score >= 6

        strong_checks = [
            delta_ok,
            volume_ok,
            price_ok,
            flow_ok
        ]

        if side == "pe" and not flow_ok:
            pe_flow_reject += 1

        if sum(strong_checks) >= 3 and same_side_count >= 1:

            if side == "pe":
                pe_pass += 1
            
            entry_score = (
                abs(dp) * 0.25 +
                min(vp, 500) * 0.35 +
                pp * 0.30 +
                flow_score * 4
            )

            entry_price = pv  # option buy price at entry candle

            exit_ts, exit_price, _, exit_reason = find_exit_after_entry(
                full, ts, stk, side, entry_price, col_map, momentum_entry=momentum_ok
            )

            entry_price = pv
            pnl_points = exit_price - entry_price if exit_price is not None else np.nan

            best_move, best_time, best_price = compute_strike_best_move(
                full, ts, stk, side, entry_price, col_map
            )

            top_rows.append((
            ts, stk, spot, side,
            entry_price, exit_ts, exit_price, pnl_points,
            best_move, best_time, best_price,
            entry_score, score, dp, gp, vp, pp,
            exit_reason,
            f"{sum(strong_checks)}/4 FLOW={flow_score} CHOP={int(r.get('chop_score', 0))} "
            f"F200={int(bool(r.get('flat200', False)))} "
            f"F20={int(bool(r.get('flat20', False)))} "
            f"F50={int(bool(r.get('flat50', False)))} "
            f"N20={int(float(r.get('nifty_close', np.nan)) >= float(r.get('ema20', np.nan)) if not pd.isna(r.get('nifty_close', np.nan)) and not pd.isna(r.get('ema20', np.nan)) else 0)} "
            f"N50={int(float(r.get('nifty_close', np.nan)) >= float(r.get('ema50', np.nan)) if not pd.isna(r.get('nifty_close', np.nan)) and not pd.isna(r.get('ema50', np.nan)) else 0)} "
            f"COMP={int(bool(r.get('ma_compression', False)))} "
            f"X={int(r.get('ema20_50_crosses', 0))} "
            f"{momentum_reason if momentum_ok else ''} {flow_reason}"
            ))
        
        else:
            if side == "pe":
                pe_strength_reject += 1 

    # First sort by ENTRY SCORE so duplicate same-time signals keep the strongest row.
    top_rows.sort(key=lambda x: x[11], reverse=True)

    # Remove duplicate timestamps: keep only strongest row from same timestamp.
    unique_rows = []
    seen_ts = set()

    for r in top_rows:
        ts = str(r[0])[:19]
        if ts in seen_ts:
            continue
        seen_ts.add(ts)
        unique_rows.append(r)

    # Print entries in proper time order, not score order.
    unique_rows.sort(key=lambda x: x[0])
    overlapping_skip_count = 0

    if not ALLOW_OVERLAPPING_TRADES:
        single_trade_rows = []
        active_until = None

        for r in unique_rows:
            entry_ts = r[0]
            exit_ts = r[5]

            if active_until is not None and entry_ts < active_until:
                overlapping_skip_count += 1
                continue

            single_trade_rows.append(r)
            active_until = exit_ts if exit_ts is not None and not pd.isna(exit_ts) else entry_ts

        unique_rows = single_trade_rows

    if USE_NIFTY_200MA_FILTER:
        print(f"  {dim('NIFTY 200 MA filter:')} {bold('ON')}   "
              f"{dim('CE blocked below MA:')} {bold(str(ce_ma_reject))}   "
              f"{dim('PE blocked above MA:')} {bold(str(pe_ma_reject))}   "
              f"{dim('MA missing:')} {bold(str(ma_missing_count))}")
    else:
        print(f"  {dim('NIFTY 200 MA filter:')} {bold('OFF')}")
    if USE_FAST_EMA_DIRECTION_FILTER:
        print(f"  {dim('Fast EMA direction filter:')} {bold('ON')}   "
              f"{dim('CE blocked below 20/50:')} {bold(str(ce_fast_ema_reject))}   "
              f"{dim('PE blocked above 20/50:')} {bold(str(pe_fast_ema_reject))}   "
              f"{dim('EMA missing:')} {bold(str(fast_ema_missing_count))}")
    else:
        print(f"  {dim('Fast EMA direction filter:')} {bold('OFF')}")
    if USE_NIFTY_CHOP_FILTER:
        print(f"  {dim('NIFTY chop filter:')} {bold('ON')}   "
              f"{dim('Threshold:')} {bold(str(CHOP_SCORE_THRESHOLD))}   "
              f"{dim('Blocked entries:')} {bold(str(chop_reject))}   "
              f"{dim('Chop missing:')} {bold(str(chop_missing_count))}")
    else:
        print(f"  {dim('NIFTY chop filter:')} {bold('OFF')}")
    if USE_PRICE_MOMENTUM_OVERRIDE:
        print(f"  {dim('Price momentum override:')} {bold('ON')}   "
              f"{dim('P% >=')} {bold(str(PRICE_MOMENTUM_ENTRY_PCT))}   "
              f"{dim('MA/chop overrides used:')} {bold(str(momentum_override_count))}")
    else:
        print(f"  {dim('Price momentum override:')} {bold('OFF')}")
    if ALLOW_OVERLAPPING_TRADES:
        print(f"  {dim('Single active trade rule:')} {bold('OFF')}   "
              f"{dim('Overlapping entries allowed')}")
    else:
        print(f"  {dim('Single active trade rule:')} {bold('ON')}   "
              f"{dim('Overlapping entries skipped:')} {bold(str(overlapping_skip_count))}")
    print()

    h_top = (
        f"  {'ENTRY TIME':<19}  {'EXIT TIME':<19}  {'STRIKE':>8}  {'SPOT':>8}  {'SIDE':>4}  "
        f"{'ENTRY':>8}  {'EXIT':>8}  {'PNL':>8}  {'BEST MOVE':>10}  {'BEST TIME':<19}  "
        f"{'ENTRY SCR':>9}  {'SYS SCR':>7}  "
        f"{'D%':>9}  {'G%':>9}  {'V%':>9}  {'P%':>9}  {'EXIT REASON':<28}"
    )
    print(bold(h_top))
    sep(W)

    for ts, stk, spot, side, entry_price, exit_ts, exit_price, pnl_points, best_move, best_time, best_price, entry_score, sys_score, dp, gp, vp, pp, exit_reason, reason in unique_rows[:TOP_N]:
        side_c = bright_green("CE") if side == "ce" else bright_red("PE")

        pnl_txt = bright_green(f"{pnl_points:>8.2f}") if pnl_points >= 0 else bright_red(f"{pnl_points:>8.2f}")
        best_txt = bright_green(f"{best_move:>10.2f}") if best_move >= 0 else bright_red(f"{best_move:>10.2f}")

        print(
            f"  {dim(str(ts)[:19])}  "
            f"{dim(str(exit_ts)[:19])}  "
            f"{cyan(f'{stk:>8.1f}')}  {cyan(f'{spot:>8.2f}')}  {side_c}  "
            f"{entry_price:>8.2f}  {exit_price:>8.2f}  {pnl_txt}  {best_txt}  "
            f"{dim(str(best_time)[:19])}  "
            f"{bold(f'{entry_score:>9.1f}')}  {bold(f'{sys_score:>7.1f}')}  "
            f"{rjust(color_pct(dp), 9)}  "
            f"{rjust(color_pct(gp), 9)}  "
            f"{rjust(color_pct(vp, 50), 9)}  "
            f"{rjust(color_pct(pp), 9)}  "
            f"{exit_reason:<28}  {reason}"
        )
    pe_rows = [x for x in unique_rows if x[3] == "pe"]

    if pe_rows:
        print()
        header("PE ENTRIES ONLY — same format", W)
        print(bold(h_top))
        sep(W)

        for ts, stk, spot, side, entry_price, exit_ts, exit_price, pnl_points, best_move, best_time, best_price, entry_score, sys_score, dp, gp, vp, pp, exit_reason, reason in pe_rows[:TOP_N]:
            side_c = bright_red("PE")

            pnl_txt = bright_green(f"{pnl_points:>8.2f}") if pnl_points >= 0 else bright_red(f"{pnl_points:>8.2f}")
            best_txt = bright_green(f"{best_move:>10.2f}") if best_move >= 0 else bright_red(f"{best_move:>10.2f}")

            print(
                f"  {dim(str(ts)[:19])}  "
                f"{dim(str(exit_ts)[:19])}  "
                f"{cyan(f'{stk:>8.1f}')}  {cyan(f'{spot:>8.2f}')}  {side_c}  "
                f"{entry_price:>8.2f}  {exit_price:>8.2f}  {pnl_txt}  {best_txt}  "
                f"{dim(str(best_time)[:19])}  "
                f"{bold(f'{entry_score:>9.1f}')}  {bold(f'{sys_score:>7.1f}')}  "
                f"{rjust(color_pct(dp), 9)}  "
                f"{rjust(color_pct(gp), 9)}  "
                f"{rjust(color_pct(vp, 50), 9)}  "
                f"{rjust(color_pct(pp), 9)}  "
                f"{exit_reason:<28}  {reason}"
            )

        sep(W)
    if not unique_rows:
        print(f"  {dim('No top entries found.')}")

    sep(W)
    print("\n========== PE DEBUG ==========")
    print("PE Layer1 rows         :", pe_total)
    print("PE overextended reject :", pe_overextended_reject)
    print("PE gamma reject        :", pe_gamma_reject)
    print("PE flow reject         :", pe_flow_reject)
    print("PE strength reject     :", pe_strength_reject)
    print("PE final entries       :", pe_pass)
    print("==============================")


    
    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    header("SUMMARY", W)

    option_pnls = [
        float(r[7]) for r in unique_rows
        if r[7] is not None and not pd.isna(r[7])
    ]
    total_option_pnl = round(sum(option_pnls), 2) if option_pnls else 0.0
    profit_count = sum(1 for pnl in option_pnls if pnl > 0)
    loss_count = sum(1 for pnl in option_pnls if pnl < 0)
    flat_count = sum(1 for pnl in option_pnls if pnl == 0)
    avg_option_pnl = round(total_option_pnl / len(option_pnls), 2) if option_pnls else 0.0

    # Summary after removing Layer 2, Layer 3, Layer 4 tables
    print(f"  {dim('Session window              :')} {bold(SESSION_START.strftime('%H:%M'))} – {bold(SESSION_END.strftime('%H:%M'))}")
    print(f"  {dim('Layer 1 — Same-candle spikes:')} {bold(str(len(layer1_rows)))}")
    print(f"  {dim('Top entries shown           :')} {bold(str(min(len(unique_rows), TOP_N)))}")
    print(f"  {dim('Option trades total         :')} {bold(str(len(option_pnls)))}")
    print(f"  {dim('Option profit count         :')} {bold(str(profit_count))}")
    print(f"  {dim('Option loss count           :')} {bold(str(loss_count))}")
    print(f"  {dim('Option flat count           :')} {bold(str(flat_count))}")
    total_pnl_txt = bright_green(f"{total_option_pnl:.2f}") if total_option_pnl >= 0 else bright_red(f"{total_option_pnl:.2f}")
    avg_pnl_txt = bright_green(f"{avg_option_pnl:.2f}") if avg_option_pnl >= 0 else bright_red(f"{avg_option_pnl:.2f}")
    print(f"  {dim('Option total PNL            :')} {bold(total_pnl_txt)}")
    print(f"  {dim('Option average PNL          :')} {bold(avg_pnl_txt)}")
    print()

    # ── Save CSV ──────────────────────────────────────────────────────────────
    save_cols = ["timestamp","strike","spot"]
    for side in sides:
        cm = col_map[side]
        save_cols += [
            cm["delta"], f"{side}_d_pct", f"{side}_d_xpct", f"{side}_d_rank", f"{side}_d_trend",
            cm["gamma"], f"{side}_g_pct", f"{side}_g_xpct", f"{side}_g_rank", f"{side}_g_trend",
            cm["volume"],f"{side}_v_pct", f"{side}_v_xpct", f"{side}_v_rank", f"{side}_v_trend",
            cm["price"], f"{side}_p_pct", f"{side}_p_xpct", f"{side}_p_rank", f"{side}_p_trend",
            cm["iv"],    f"{side}_score", f"{side}_same_spike",
            f"{side}_cross_bull", f"{side}_cross_bear",
        ]


if __name__ == "__main__":
    main()
