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
"""

import re
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import time as dtime

# ══════════════════════════════════════════════════════════════════════════════
# USER CONFIG
# ══════════════════════════════════════════════════════════════════════════════
CSV_PATH         = "oi_2026_06_16.csv"
ANALYSIS_DATE    = "2026-06-16"
SIDE             = "both"          # "ce" | "pe" | "both"
CROSS_CANDLES    = 5               # lookback window for cross-candle trend
STRIKES_NEARBY   = 2
ATM_RANGE_POINTS  = 100
STRIKE_STEP       = 50
STRENGTH_PCT     = 60              # percentile threshold for "strong" (runtime)
WEAK_PCT         = 40              # percentile threshold for "weak"  (runtime)

SESSION_START    = dtime(9, 20)    # filter: keep rows from this time onward
SESSION_END      = dtime(15, 30)   # filter: keep rows up to this time
OUT_CSV          = "strength_report.csv"
OUT_XLSX         = "strength_report.xlsx"
TOP_N = 20

# Exit rule:
# For CE/PE buy, exit when any 3 of Delta%, Gamma%, Volume%, Price% become negative.
EXIT_NEG_COUNT = 3
# EXIT CONFIG
MIN_HOLD_BARS = 10          # don't exit immediately after entry
EXIT_WEAK_BARS = 3          # need 3 continuous weak candles
TRAIL_DROP_PTS = 25         # exit if option falls 25 pts from best price

ENTRY_CUTOFF = dtime(15, 0)   # no new entries after 3 PM
FORCE_EXIT   = dtime(15, 0)   # force exit at/after 3 PM
TRAIL_ACTIVATE_PTS = 30     # trailing starts only after +30 pts profit
TRAIL_LOCK_PTS     = 20     # after activation, protect 20 pts profit
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

def find_exit_after_entry(full, entry_ts, strike, side, entry_price, col_map):
    cm = col_map[side]

    trade = full[
        (full["timestamp"] > entry_ts) &
        (full["strike"] == strike)
    ].copy().sort_values("timestamp").reset_index(drop=True)

    if trade.empty:
        return entry_ts, entry_price, 0, "No future data"

    best_price = entry_price
    weak_count = 0

    for i, r in trade.iterrows():
        price = r[cm["price"]]

        # Force exit at 3 PM
        if r["timestamp"].time() >= FORCE_EXIT:
            pnl = price - entry_price
            return r["timestamp"], price, pnl, "Exit: 3 PM force exit"
        
        price = r[cm["price"]]
        best_price = max(best_price, price)

        # Do not exit too early
        if i < MIN_HOLD_BARS:
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

        # Exit only after continuous weakness + price drop
                # Profit trailing stop:
        # Example: entry 179, best 270
        # trail_sl = 270 - 25 = 245
        # If price falls to 245, exit and protect profit
        if best_price >= entry_price + TRAIL_ACTIVATE_PTS:
            trail_sl = max(entry_price + TRAIL_LOCK_PTS, best_price - TRAIL_DROP_PTS)

            if price <= trail_sl:
                pnl = price - entry_price
                return r["timestamp"], price, pnl, "Exit: profit trailing SL"

        # Weakness exit only if trade never moved enough in profit
        if weak_count >= EXIT_WEAK_BARS and best_price < entry_price + TRAIL_ACTIVATE_PTS:
            pnl = price - entry_price
            return r["timestamp"], price, pnl, "Exit: weak before profit"

    last = trade.iloc[-1]
    exit_price = last[cm["price"]]
    pnl = exit_price - entry_price
    return last["timestamp"], exit_price, pnl, "Exit: session end"
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
    print("Available dates:", sorted(df["timestamp"].dt.date.unique())[:20])

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

    top_rows = []

    for row in layer1_rows:
        ts, stk, spot, side, score, dv, dp, gv, gp, vv, vp, pv, pp, iv = row

         # No fresh entries after 3 PM
        if ts.time() >= ENTRY_CUTOFF:
            continue

        # Keep only clean buying strength rows
        # Entry condition:
        # We need option buying strength.
        # Delta, gamma, volume, price should mostly increase.
        strong_checks = [
            dp > 3,      # delta increasing
            gp > 2,      # gamma increasing
            vp > 30,     # volume increasing
            pp > 1       # option price increasing
        ]

        # Allow entry when at least 3 out of 4 are strong
        if sum(strong_checks) >= 3:
            entry_score = (
                dp * 0.35 +
                gp * 0.25 +
                min(vp, 300) * 0.25 +
                pp * 0.15
            )

            entry_price = pv  # option buy price at entry candle

            exit_ts, exit_price, _, exit_reason = find_exit_after_entry(
                full, ts, stk, side, entry_price, col_map
            )

            entry_price = pv
            pnl_points = exit_price - entry_price if exit_price is not None else np.nan

            top_rows.append((
            ts, stk, spot, side,
            entry_price, exit_ts, exit_price, pnl_points,
            entry_score, score, dp, gp, vp, pp,
            exit_reason,
            f"{sum(strong_checks)}/4 D,G,V,P strong"
        ))

    # Sort strongest first
    # Sort by ENTRY SCORE, not entry price
    top_rows.sort(key=lambda x: x[8], reverse=True)

    # Remove duplicate timestamps: keep only strongest row from same timestamp
    unique_rows = []
    seen_ts = set()

    for r in top_rows:
        ts = str(r[0])[:19]
        if ts in seen_ts:
            continue
        seen_ts.add(ts)
        unique_rows.append(r)

    h_top = (
        f"  {'ENTRY TIME':<19}  {'EXIT TIME':<19}  {'STRIKE':>8}  {'SPOT':>8}  {'SIDE':>4}  "
        f"{'ENTRY':>8}  {'EXIT':>8}  {'PNL':>8}  "
        f"{'ENTRY SCR':>9}  {'SYS SCR':>7}  "
        f"{'D%':>9}  {'G%':>9}  {'V%':>9}  {'P%':>9}  {'EXIT REASON':<28}"
    )
    print(bold(h_top))
    sep(W)

    for ts, stk, spot, side, entry_price, exit_ts, exit_price, pnl_points, entry_score, sys_score, dp, gp, vp, pp, exit_reason, reason in unique_rows[:TOP_N]:
        side_c = bright_green("CE") if side == "ce" else bright_red("PE")

        pnl_txt = bright_green(f"{pnl_points:>8.2f}") if pnl_points >= 0 else bright_red(f"{pnl_points:>8.2f}")

        print(
            f"  {dim(str(ts)[:19])}  "
            f"{dim(str(exit_ts)[:19])}  "
            f"{cyan(f'{stk:>8.1f}')}  {cyan(f'{spot:>8.2f}')}  {side_c}  "
            f"{entry_price:>8.2f}  {exit_price:>8.2f}  {pnl_txt}  "
            f"{bold(f'{entry_score:>9.1f}')}  {bold(f'{sys_score:>7.1f}')}  "
            f"{rjust(color_pct(dp), 9)}  "
            f"{rjust(color_pct(gp), 9)}  "
            f"{rjust(color_pct(vp, 50), 9)}  "
            f"{rjust(color_pct(pp), 9)}  "
            f"{exit_reason:<28}"
        )

    if not unique_rows:
        print(f"  {dim('No top entries found.')}")

    sep(W)


    
    # ══════════════════════════════════════════════════════════════════════════
    # SUMMARY
    # ══════════════════════════════════════════════════════════════════════════
    header("SUMMARY", W)

    # Summary after removing Layer 2, Layer 3, Layer 4 tables
    print(f"  {dim('Session window              :')} {bold(SESSION_START.strftime('%H:%M'))} – {bold(SESSION_END.strftime('%H:%M'))}")
    print(f"  {dim('Layer 1 — Same-candle spikes:')} {bold(str(len(layer1_rows)))}")
    print(f"  {dim('Top entries shown           :')} {bold(str(min(len(unique_rows), 20)))}")
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
    full[[c for c in save_cols if c in full.columns]].to_csv(OUT_CSV, index=False)
    print(f"  {bright_green('✅')} Saved → {OUT_CSV}")

    # ── Save XLSX (multi-sheet with colours) ─────────────────────────────────
    # Layer 2/4 removed from console, so pass empty rows to Excel export
    _export_xlsx(full, layer1_rows, [], [], sides, col_map, save_cols, timestamps)
    print(f"  {bright_green('✅')} Saved → {OUT_XLSX}\n")


if __name__ == "__main__":
    main()