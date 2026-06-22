r"""

python -m py_compile .\3_strength_analyser.py
default command to check oi buildup and strength report for a single CSV file and date:
python .\3_strength_analyser.py --csv oi_2024_01_02.csv --date 2024-01-02

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

RUN MODES / COMMANDS

  1. DEFAULT FULL MODE
     Command:
       python 3_strength_analyser.py

     What it does:
       - Uses hardcoded CSV_PATH and ANALYSIS_DATE from USER CONFIG below.
       - Prints the full OI buildup table from SESSION_START to SESSION_END.
       - Prints top entries with entry/exit, PNL, best move PNL, best time,
         delta %, gamma %, volume %, price %, and exit reason.
       - Prints PE debug and final option trade summary.

     Optional single-file argparse override:
       python 3_strength_analyser.py --csv oi_2024_12_31.csv --date 2024-12-31

     This still uses full mode output because --monthly is not passed.

  2. COMPACT MONTHLY MODE
     Command:
       python 3_strength_analyser.py --monthly --month jan --year 2024

     Month can be name or number:
       python 3_strength_analyser.py --monthly --month january --year 2024
       python 3_strength_analyser.py --monthly --month 1 --year 2024

     If CSV files are in another folder:
       python 3_strength_analyser.py --monthly --month jan --year 2024 --csv-dir C:\path\to\csvs

     What it does:
       - Scans weekly expiry CSVs named oi_YYYY_MM_DD.csv.
       - Reads the timestamp column inside each CSV.
       - Runs every actual trading date that falls in the selected month.
       - If the same trading date appears in multiple weekly CSVs, the script
         picks the nearest weekly expiry CSV for that date.
       - Example: oi_2024_11_26.csv can run 2024-11-22 because that trading
         date exists inside the CSV.
       - Runs each matching trading date quietly.
       - Does NOT print the OI buildup table.
       - Prints only compact date-by-date summary:
           CSV file, date, trades, profit count, loss count, flat count,
           total PNL, and best move PNL.
       - Prints every entry under that date with entry/exit, side, strike,
         PNL, best move, Greeks/volume/price %, and exit reason.
       - Prints one TOTAL row for the selected month.

     Monthly expiry rule:
       - Weekly expiry CSVs dated inside the selected month are included.
       - By default, first 7 days of next month are also included because
         weekly expiry can fall between month-end and the next month's first week.

     To use only the selected calendar month and skip next month's first week:
       python 3_strength_analyser.py --monthly --month jan --year 2024 --no-next-week

  3. HELP
     Command:
       python 3_strength_analyser.py --help

  4. MONTHLY MODE WITH FULL ENTRY CONFIG
     Command:
       python 3_strength_analyser.py --monthly --month february --year 2024 --no-next-week --entry-start 09:45 --flow 10 --same-side 2 --late-start 14:15 --late-flow 12 --early-entry --early-start 09:25 --early-flow 16 --early-same-side 3 --early-opp 2 --early-price-pct 6 --early-volume-pct 40 --early-no-cross-confirm --no-relax-cross-side

     Change --month and --year for the month you want to test.

     Config explanation:
       --monthly
         Runs compact monthly summary mode instead of full single-day table.

       --month february
         Selects the month. You can use name or number, e.g. february, feb, 2.

       --year 2024
         Selects the year for monthly mode.

       --no-next-week
         Uses only dates inside the selected calendar month. Without this,
         the first 7 days of next month are also included for weekly expiry
         continuity.

       --entry-start 09:45
         Normal entries start only from 09:45. This avoids many gap-open
         option spikes between 09:20 and 09:44.

       --flow 10
         Minimum cross-strike FLOW score for normal entries. Higher value
         means fewer entries but stronger nearby-strike confirmation.

       --same-side 2
         Minimum same-side confirming strikes. Example for CE: at least 2
         nearby CE strikes should show supportive buildup.

       --late-start 14:15
         After 14:15, late-entry rules apply because there is less time left
         before the 3 PM force exit.

       --late-flow 12
         Minimum FLOW required after --late-start. This blocks weak late
         entries unless confirmation is stronger than normal.

       --early-entry
         Enables special early OI entries before 09:45. Without this flag,
         entries before --entry-start are blocked.

       --early-start 09:25
         Earliest time allowed for early OI entries. Here, early window is
         09:25 to 09:44.

       --early-flow 16
         Minimum FLOW score for early OI entries. Early entries need stronger
         confirmation than normal entries because open-period moves can reverse.

       --early-same-side 3
         Minimum same-side confirming strikes for early OI entries.

       --early-opp 2
         Minimum opposite-side support strikes for early OI entries.
         CE example: PE side should also confirm by weakening/selling pressure.

       --early-price-pct 6
         Minimum option price percentage increase for early OI entries.

       --early-volume-pct 40
         Minimum option volume percentage increase for early OI entries.

       --early-no-cross-confirm
         Allows early entries even if reason does not contain OI_BULL/OI_BEAR.
         This gives more entries for debugging, but it is looser and can add
         bad open-period trades.

       --no-relax-cross-side
         Disables the relaxed same-side rule. With this flag, the script uses
         the direct --same-side requirement and does not relax it just because
         OI_BULL/OI_BEAR exists.

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

  5. Bad-move based stop loss
     BAD MOVE shows the worst option-price move after entry.
     If BEST MOVE is large but BAD MOVE is only slightly below the old stop,
     the entry was good but the stop was too tight.

     Stop logic:
       - normal entries: 30 points
       - price-momentum entries: 45 points
       - super-strong price momentum + flow entries: 60 points

     Super-strong means:
       - PRICE_MOMENTUM entry
       - FLOW >= SUPER_MOMENTUM_FLOW_SCORE
       - same-side build >= SUPER_MOMENTUM_SIDE_COUNT
       - opposite-side support >= SUPER_MOMENTUM_SIDE_COUNT

  6. Strict price-momentum override quality
     A high option price % candle alone is not enough. In October/December logs,
     many losing trades had P% > 10 but BEST MOVE was tiny and BAD MOVE was deep.
     That means the candle was only a spike, not a supported trend.

     If price momentum is used to bypass the 200MA/chop filter, require:
       - FLOW >= MOMENTUM_OVERRIDE_MIN_FLOW
       - same-side build >= MOMENTUM_OVERRIDE_MIN_SAME_SIDE
       - opposite-side support >= MOMENTUM_OVERRIDE_MIN_OPP_SUPPORT
       - EMA20 and EMA50 slope moving with trade direction

     Example:
       CE entry needs CE_BUY plus PE_SELL support.
       PE entry needs PE_BUY plus CE_SELL support.

  7. Entry-quality hard filters
     These filters target the biggest bad-move patterns from the monthly logs:

       - ENTRY_START = 09:45
         Blocks gap-open option spikes. Before 09:45, option price often jumps
         at the top of the opening move and then mean-reverts.

       - MIN_ENTRY_FLOW_SCORE = 10
         Requires stronger nearby-strike confirmation before entry.

       - MIN_SAME_SIDE_COUNT = 2
         One nearby strike can be noise. Two same-side strikes is better flow.

       - DAILY_LOSS_LIMIT = 2 with DAILY_LOSS_CUTOFF = 13:00
         If two accepted trades are already losses, skip new entries after 13:00.
         This avoids repeated chop re-entries late in the day.

       - LATE_ENTRY_START = 14:15 and LATE_ENTRY_MIN_FLOW = 12
         Late trades need stronger confirmation because there is less time for
         the move to develop before the 3 PM force exit.

  8. Cross-side OI buildup confirmation
     This catches the strong entry pattern seen in the shared OI buildup logs:

       Bullish CE entry:
         - CE nearby strikes: delta up, volume up, option price up.
         - PE nearby strikes: delta weakening, volume up, option price down.
         - If both sides confirm across enough strikes, reason shows OI_BULL.

       Bearish PE entry:
         - PE nearby strikes: volume up and option price up.
         - CE nearby strikes: delta weakening, volume up, option price down.
         - If both sides confirm across enough strikes, reason shows OI_BEAR.

     Gamma is used as a bonus, not a hard requirement, because option gamma can
     rise on both sides during fast moves.

  9. Optional early super-strong OI entry
     Normal entries still start at ENTRY_START = 09:45.
     With --early-entry, the script can accept 09:25-09:45 entries only when
     the OI buildup is very strong:
       - FLOW >= EARLY_ENTRY_MIN_FLOW
       - same-side strikes >= EARLY_ENTRY_MIN_SAME_SIDE
       - opposite-side support >= EARLY_ENTRY_MIN_OPP_SUPPORT
       - option price % >= EARLY_ENTRY_MIN_PRICE_PCT
       - option volume % >= EARLY_ENTRY_MIN_VOLUME_PCT
       - reason contains OI_BULL for CE or OI_BEAR for PE

     This is meant for days like 2024-02-05 where CE buildup started strongly
     before 09:45. It is not a blanket open-gap entry unlock.
"""

import argparse
import contextlib
import io
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
CSV_PATH         = "oi_2024_01_02.csv"
ANALYSIS_DATE    = "2024-01-01"
SIDE             = "both"          # "ce" | "pe" | "both"
CROSS_CANDLES    = 5               # lookback window for cross-candle trend
STRIKES_NEARBY   = 2
ATM_RANGE_POINTS  = 500
STRIKE_STEP       = 50
STRENGTH_PCT     = 60              # percentile threshold for "strong" (runtime)
WEAK_PCT         = 40              # percentile threshold for "weak"  (runtime)
OI_TABLE_PRICE_PCT = 3             # also show rows where option price builds >= 3%
OI_TABLE_VOLUME_PCT = 3            # and option volume builds >= 3%
OI_TABLE_PRICE_DROP_PCT = -3       # also show opposite-side weakness when price falls <= -3%

SESSION_START    = dtime(9, 20)    # filter: keep rows from this time onward
SESSION_END      = dtime(15, 30)   # filter: keep rows up to this time
OUT_CSV          = "strength_report.csv"
OUT_XLSX         = "strength_report.xlsx"
TOP_N = 20
ALLOW_OVERLAPPING_TRADES = False  # False = one active trade only; next entry after exit

# Entry-quality filters from monthly bad-move review.
ENTRY_START = dtime(9, 45)       # avoid gap-open option spikes before 09:45
MIN_ENTRY_FLOW_SCORE = 10        # was 6; require stronger cross-strike flow
MIN_SAME_SIDE_COUNT = 2          # was 1; avoid single-strike noise entries
DAILY_LOSS_LIMIT = 2             # after this many losses, late re-entry is blocked
DAILY_LOSS_CUTOFF = dtime(13, 0) # after 13:00, stop re-entering if day already failed
LATE_ENTRY_START = dtime(14, 15)
LATE_ENTRY_MIN_FLOW = 12
USE_EARLY_OI_ENTRY = False
EARLY_ENTRY_START = dtime(9, 25)
EARLY_ENTRY_MIN_FLOW = 16
EARLY_ENTRY_MIN_SAME_SIDE = 3
EARLY_ENTRY_MIN_OPP_SUPPORT = 2
EARLY_ENTRY_MIN_PRICE_PCT = 6
EARLY_ENTRY_MIN_VOLUME_PCT = 40
EARLY_REQUIRE_CROSS_CONFIRM = True
RELAX_SAME_SIDE_ON_CROSS_CONFIRM = True
RELAXED_MIN_SAME_SIDE = 1
RELAXED_MIN_OPP_SUPPORT = 2

# Exit rule:
# For CE/PE buy, exit when any 3 of Delta%, Gamma%, Volume%, Price% become negative.
EXIT_NEG_COUNT = 3
# EXIT CONFIG
MIN_HOLD_BARS = 20          # don't exit immediately after entry
EXIT_WEAK_BARS = 5          # need 3 continuous weak candles
TRAIL_DROP_PTS = 40         # exit if option falls 25 pts from best price
STOP_LOSS_PTS = 30          # base fixed max loss from entry price
MOMENTUM_STOP_LOSS_PTS = 45 # strong price-momentum entries need more room
SUPER_MOMENTUM_STOP_LOSS_PTS = 60
SUPER_MOMENTUM_FLOW_SCORE = 16
SUPER_MOMENTUM_SIDE_COUNT = 4
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
    (100, 78, 25),
    (70, 48, 25),
    (40, 28, 22),
    (25,  18, 18),
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
STRICT_MOMENTUM_OVERRIDE_QUALITY = True
MOMENTUM_OVERRIDE_MIN_FLOW = 12
MOMENTUM_OVERRIDE_MIN_SAME_SIDE = 3
MOMENTUM_OVERRIDE_MIN_OPP_SUPPORT = 2
MOMENTUM_OVERRIDE_EMA20_SLOPE_MIN = 3
MOMENTUM_OVERRIDE_EMA50_SLOPE_MIN = 2

# Cross-side OI buildup confirmation:
# Bullish setup = CE buying across nearby strikes + PE selling confirmation.
# Bearish setup = PE buying across nearby strikes + CE selling confirmation.
# This is based on the daily OI buildup examples:
#   CE: delta up, volume up, price up.
#   PE opposite: delta weakens, volume up, price down.
# Gamma is a score bonus only, because gamma can expand on both sides.
OI_BUILD_MIN_BUY_D_PCT = 6
OI_BUILD_MIN_BUY_G_PCT = 2
OI_BUILD_MIN_BUY_V_PCT = 40
OI_BUILD_MIN_BUY_P_PCT = 8
OI_BUILD_MIN_SELL_D_DROP_PCT = 3
OI_BUILD_MIN_SELL_V_PCT = 40
OI_BUILD_MIN_SELL_P_DROP_PCT = 5
OI_BUILD_MIN_BUY_STRIKES = 2
OI_BUILD_MIN_SELL_STRIKES = 2
OI_BUILD_STRONG_BONUS = 4
OI_BUILD_GAMMA_BONUS_PER_STRIKE = 1

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
_NIFTY_200MA_CACHE = None
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

def parse_month(value):
    raw = str(value).strip().lower()
    names = {
        "jan": 1, "january": 1,
        "feb": 2, "february": 2,
        "mar": 3, "march": 3,
        "apr": 4, "april": 4,
        "may": 5,
        "jun": 6, "june": 6,
        "jul": 7, "july": 7,
        "aug": 8, "august": 8,
        "sep": 9, "sept": 9, "september": 9,
        "oct": 10, "october": 10,
        "nov": 11, "november": 11,
        "dec": 12, "december": 12,
    }
    if raw in names:
        return names[raw]
    month = int(raw)
    if month < 1 or month > 12:
        raise ValueError("month must be 1-12 or month name like jan")
    return month

def parse_time_arg(value):
    try:
        hour, minute = str(value).strip().split(":", 1)
        return dtime(int(hour), int(minute))
    except Exception as exc:
        raise argparse.ArgumentTypeError(f"Invalid time '{value}'. Use HH:MM, e.g. 09:25") from exc

def month_name(month):
    return pd.Timestamp(2000, month, 1).strftime("%B")

def date_from_oi_filename(path):
    match = re.search(r"oi_(\d{4})_(\d{2})_(\d{2})", Path(path).stem)
    if not match:
        return None
    yyyy, mm, dd = match.groups()
    return pd.Timestamp(int(yyyy), int(mm), int(dd)).date()

def monthly_date_range(year, month, include_next_week=True):
    start = pd.Timestamp(year, month, 1)
    end = start + pd.offsets.MonthEnd(0)
    if include_next_week:
        end = end + pd.Timedelta(days=7)
    return start.date(), end.date()

def trading_dates_in_csv(csv_file):
    try:
        dates = pd.read_csv(csv_file, usecols=["timestamp"], parse_dates=["timestamp"])
    except Exception:
        file_date = date_from_oi_filename(csv_file)
        return [file_date] if file_date else []

    if dates.empty:
        return []

    return sorted(dates["timestamp"].dt.date.dropna().unique())

def monthly_signal_date(csv_file):
    file_date = date_from_oi_filename(csv_file)
    dates = trading_dates_in_csv(csv_file)
    if not dates:
        return file_date
    if not file_date:
        return dates[-1]

    before_expiry = [d for d in dates if d < file_date]
    fridays = [d for d in before_expiry if pd.Timestamp(d).weekday() == 4]
    if fridays:
        return fridays[-1]
    if before_expiry:
        return before_expiry[-1]
    if file_date in dates:
        return file_date
    return dates[-1]

def load_nifty_200ma():
    global _NIFTY_200MA_CACHE

    if not USE_NIFTY_200MA_FILTER:
        return None

    if _NIFTY_200MA_CACHE is not None:
        return _NIFTY_200MA_CACHE

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
    nifty["ema20_slope"] = nifty["ema20"] - nifty["ema20"].shift(FLAT_20_LOOKBACK)
    nifty["ema50_slope"] = nifty["ema50"] - nifty["ema50"].shift(FLAT_50_LOOKBACK)

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

    _NIFTY_200MA_CACHE = nifty[[
        "timestamp", "nifty_close", "nifty_ma200", "ema20", "ema50",
        "ema20_slope", "ema50_slope",
        "flat200", "flat50", "flat20", "ma_compression", "many_crosses",
        "small_range", "ema20_50_crosses", "avg_range20", "chop_score",
    ]].dropna(subset=["nifty_ma200"])
    return _NIFTY_200MA_CACHE

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

def momentum_override_slope_ok(row, side):
    slope20 = row.get("ema20_slope", np.nan)
    slope50 = row.get("ema50_slope", np.nan)
    if pd.isna(slope20) or pd.isna(slope50):
        return True

    if side == "ce":
        return (
            slope20 >= MOMENTUM_OVERRIDE_EMA20_SLOPE_MIN and
            slope50 >= MOMENTUM_OVERRIDE_EMA50_SLOPE_MIN
        )

    return (
        slope20 <= -MOMENTUM_OVERRIDE_EMA20_SLOPE_MIN and
        slope50 <= -MOMENTUM_OVERRIDE_EMA50_SLOPE_MIN
    )

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

def adaptive_stop_loss_pts(momentum_entry=False, flow_score=0, same_side_count=0, opp_side_count=0):
    """
    Bad-move analysis showed that strong momentum entries can dip slightly
    beyond the old fixed stop and then make the real move later.

    Base entries use 30 pts.
    Momentum entries use 45 pts.
    Super-strong momentum flow uses 60 pts:
      - price momentum entry
      - FLOW >= SUPER_MOMENTUM_FLOW_SCORE
      - same-side build and opposite-side support both strong
    """
    if not momentum_entry:
        return STOP_LOSS_PTS

    if (
        flow_score >= SUPER_MOMENTUM_FLOW_SCORE and
        same_side_count >= SUPER_MOMENTUM_SIDE_COUNT and
        opp_side_count >= SUPER_MOMENTUM_SIDE_COUNT
    ):
        return SUPER_MOMENTUM_STOP_LOSS_PTS

    return MOMENTUM_STOP_LOSS_PTS

def find_exit_after_entry(
    full,
    entry_ts,
    strike,
    side,
    entry_price,
    col_map,
    momentum_entry=False,
    flow_score=0,
    same_side_count=0,
    opp_side_count=0,
):
    cm = col_map[side]
    stop_loss_pts = adaptive_stop_loss_pts(
        momentum_entry=momentum_entry,
        flow_score=flow_score,
        same_side_count=same_side_count,
        opp_side_count=opp_side_count,
    )

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

        if pnl_now <= -stop_loss_pts:
            pnl = price - entry_price
            return r["timestamp"], price, pnl, f"Exit: stop loss -{stop_loss_pts}"

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

def compute_strike_bad_move(full, entry_ts, strike, side, entry_price, col_map):
    """
    Bad move for the SAME STRIKE only.
    Shows the maximum adverse option-price move after entry.
    """
    cm = col_map[side]
    future = full[
        (full["timestamp"] > entry_ts) &
        (full["strike"] == strike)
    ].copy().sort_values("timestamp")

    if future.empty:
        return 0.0, entry_ts, entry_price

    low_idx = future[cm["price"]].astype(float).idxmin()
    low_row = future.loc[low_idx]
    low_price = float(low_row[cm["price"]])
    bad_move = low_price - float(entry_price)

    return round(bad_move, 2), low_row["timestamp"], round(low_price, 2)

def get_flow_confirm(full, ts, strike, side):
    """
    Cross-side OI buildup confirmation.

    Bullish:
      CE nearby strikes show delta + volume + price expansion.
      PE nearby strikes show weakening delta + volume build + price fall.

    Bearish:
      PE nearby strikes show volume + price expansion.
      CE nearby strikes show weakening delta + volume build + price fall.

    Gamma gives a bonus only; it is not required because gamma can rise on both
    CE and PE during fast option repricing.
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
    ce_gamma_bonus = 0
    pe_gamma_bonus = 0

    for _, r in nearby.iterrows():
        ce_buying = (
            r["ce_d_pct"] >= OI_BUILD_MIN_BUY_D_PCT and
            r["ce_v_pct"] >= OI_BUILD_MIN_BUY_V_PCT and
            r["ce_p_pct"] >= OI_BUILD_MIN_BUY_P_PCT
        )
        pe_selling = (
            r["pe_d_pct"] <= -OI_BUILD_MIN_SELL_D_DROP_PCT and
            r["pe_v_pct"] >= OI_BUILD_MIN_SELL_V_PCT and
            r["pe_p_pct"] <= -OI_BUILD_MIN_SELL_P_DROP_PCT
        )
        pe_buying = (
            r["pe_v_pct"] >= OI_BUILD_MIN_BUY_V_PCT and
            r["pe_p_pct"] >= OI_BUILD_MIN_BUY_P_PCT
        )
        ce_selling = (
            r["ce_d_pct"] <= -OI_BUILD_MIN_SELL_D_DROP_PCT and
            r["ce_v_pct"] >= OI_BUILD_MIN_SELL_V_PCT and
            r["ce_p_pct"] <= -OI_BUILD_MIN_SELL_P_DROP_PCT
        )

        if ce_buying:
            ce_buy += 1
            if r["ce_g_pct"] >= OI_BUILD_MIN_BUY_G_PCT:
                ce_gamma_bonus += OI_BUILD_GAMMA_BONUS_PER_STRIKE

        if pe_selling:
            pe_sell += 1

        if pe_buying:
            pe_buy += 1
            if r["pe_g_pct"] >= OI_BUILD_MIN_BUY_G_PCT:
                pe_gamma_bonus += OI_BUILD_GAMMA_BONUS_PER_STRIKE

        if ce_selling:
            ce_sell += 1

    if side == "ce":
        strong_cross_side = (
            ce_buy >= OI_BUILD_MIN_BUY_STRIKES and
            pe_sell >= OI_BUILD_MIN_SELL_STRIKES
        )
        flow_score = ce_buy * 2 + pe_sell * 2 + ce_gamma_bonus
        tags = []
        if strong_cross_side:
            flow_score += OI_BUILD_STRONG_BONUS
            tags.append("OI_BULL")
        if ce_gamma_bonus:
            tags.append(f"CE_GBONUS={ce_gamma_bonus}")
        reason = f"CE_BUY={ce_buy} PE_SELL={pe_sell}"
        if tags:
            reason += " " + " ".join(tags)
        return flow_score, ce_buy, pe_sell, reason

    strong_cross_side = (
        pe_buy >= OI_BUILD_MIN_BUY_STRIKES and
        ce_sell >= OI_BUILD_MIN_SELL_STRIKES
    )
    flow_score = pe_buy * 2 + ce_sell * 2 + pe_gamma_bonus
    tags = []
    if strong_cross_side:
        flow_score += OI_BUILD_STRONG_BONUS
        tags.append("OI_BEAR")
    if pe_gamma_bonus:
        tags.append(f"PE_GBONUS={pe_gamma_bonus}")
    reason = f"PE_BUY={pe_buy} CE_SELL={ce_sell}"
    if tags:
        reason += " " + " ".join(tags)
    return flow_score, pe_buy, ce_sell, reason

def has_cross_side_oi_confirm(side, flow_reason):
    if side == "ce":
        return "OI_BULL" in flow_reason
    return "OI_BEAR" in flow_reason

def early_oi_entry_ok(ts, side, pp, vp, flow_score, same_side_count, opp_side_count, flow_reason):
    """
    Optional 09:25-09:45 unlock for only the strongest OI buildup patterns.
    This catches early CE_BUY + PE_SELL / PE_BUY + CE_SELL confirmation without
    reopening weak gap-spike entries.
    """
    if not USE_EARLY_OI_ENTRY:
        return False
    if not (EARLY_ENTRY_START <= ts.time() < ENTRY_START):
        return False
    if EARLY_REQUIRE_CROSS_CONFIRM and not has_cross_side_oi_confirm(side, flow_reason):
        return False
    return (
        flow_score >= EARLY_ENTRY_MIN_FLOW and
        same_side_count >= EARLY_ENTRY_MIN_SAME_SIDE and
        opp_side_count >= EARLY_ENTRY_MIN_OPP_SUPPORT and
        pp >= EARLY_ENTRY_MIN_PRICE_PCT and
        vp >= EARLY_ENTRY_MIN_VOLUME_PCT
    )

def same_side_entry_ok(side, same_side_count, opp_side_count, flow_reason):
    if same_side_count >= MIN_SAME_SIDE_COUNT:
        return True
    if not RELAX_SAME_SIDE_ON_CROSS_CONFIRM:
        return False
    return (
        same_side_count >= RELAXED_MIN_SAME_SIDE and
        opp_side_count >= RELAXED_MIN_OPP_SUPPORT and
        has_cross_side_oi_confirm(side, flow_reason)
    )
# ══════════════════════════════════════════════════════════════════════════════
# CORE FUNCTIONS
# ══════════════════════════════════════════════════════════════════════════════
def _finite_pct(value):
    if value is None or pd.isna(value) or not np.isfinite(float(value)):
        return 0.0
    return float(value)

def _count_true(mask):
    return int(mask.fillna(False).sum())

def build_snapshot_analysis(full):
    """
    Per timestamp OI read for display after each complete snapshot.
    """
    analysis = {}
    prev_state = {"ce": None, "pe": None}
    state_streak = {"ce": 0, "pe": 0}
    prev_strong_side = None
    strong_streak = 0

    def side_snapshot(snap, side):
        p = snap[f"{side}_p_pct"].map(_finite_pct)
        v = snap[f"{side}_v_pct"].map(_finite_pct)
        d = snap[f"{side}_d_pct"].map(_finite_pct)
        g = snap[f"{side}_g_pct"].map(_finite_pct)
        n = max(1, len(snap))

        long_build = _count_true((p >= OI_BUILD_MIN_BUY_P_PCT) & (v >= OI_BUILD_MIN_BUY_V_PCT) & (d > 0))
        short_cover = _count_true((p >= OI_BUILD_MIN_BUY_P_PCT) & (v < 0))
        unwind = _count_true((p <= -OI_BUILD_MIN_SELL_P_DROP_PCT) & (v < 0))
        sell_build = _count_true((p <= -OI_BUILD_MIN_SELL_P_DROP_PCT) & (v >= OI_BUILD_MIN_BUY_V_PCT))
        delta_up = _count_true(d > 0)
        gamma_up = _count_true(g > 0)

        avg_p = float(p.mean())
        avg_v = float(v.mean())
        avg_d = float(d.mean())
        avg_g = float(g.mean())

        if long_build >= 2:
            state = "LONG_BUILD"
            label = f"fresh long build {long_build}/{n} (price+volume+delta up)"
            strength = long_build * 3 + delta_up + gamma_up
        elif short_cover >= 3:
            state = "SHORT_COVER"
            label = f"short covering {short_cover}/{n} (price up, volume down; not fresh build)"
            strength = short_cover * 2 + delta_up
        elif unwind >= 3:
            state = "UNWINDING"
            label = f"unwinding/buyers exiting {unwind}/{n} (price+volume down)"
            strength = -unwind * 3
        elif sell_build >= 3:
            state = "SELL_BUILD"
            label = f"sell pressure {sell_build}/{n} (price down, volume up)"
            strength = -sell_build * 2
        elif delta_up >= 3 and avg_p > 0:
            state = "SLOW_ACCUM"
            label = f"slow accumulation {delta_up}/{n} (delta+price improving)"
            strength = delta_up + gamma_up
        else:
            state = "MIXED"
            label = f"mixed/no clear build (Pavg {avg_p:.2f}%, Vavg {avg_v:.2f}%)"
            strength = 0

        return {
            "state": state,
            "label": label,
            "strength": strength,
            "long_build": long_build,
            "short_cover": short_cover,
            "unwind": unwind,
            "sell_build": sell_build,
            "delta_up": delta_up,
            "gamma_up": gamma_up,
            "avg_p": avg_p,
            "avg_v": avg_v,
            "avg_d": avg_d,
            "avg_g": avg_g,
            "n": n,
        }

    for ts, snap in full.groupby("timestamp", sort=True):
        ce = side_snapshot(snap, "ce")
        pe = side_snapshot(snap, "pe")

        for side, info in (("ce", ce), ("pe", pe)):
            if info["state"] == prev_state[side] and info["state"] != "MIXED":
                state_streak[side] += 1
            else:
                state_streak[side] = 1
                prev_state[side] = info["state"]

        ce_has_build = ce["state"] in ("LONG_BUILD", "SLOW_ACCUM")
        pe_has_build = pe["state"] in ("LONG_BUILD", "SLOW_ACCUM")
        ce_has_unwind = ce["state"] in ("UNWINDING", "SELL_BUILD") or ce["unwind"] >= 3 or ce["avg_p"] < -3
        pe_has_unwind = pe["state"] in ("UNWINDING", "SELL_BUILD") or pe["unwind"] >= 3 or pe["avg_p"] < -3

        if pe["strength"] > ce["strength"] + 3 and pe_has_build and ce_has_unwind:
            strong_side = "PE"
        elif ce["strength"] > pe["strength"] + 3 and ce_has_build and pe_has_unwind:
            strong_side = "CE"
        else:
            strong_side = "MIXED"

        if strong_side == prev_strong_side and strong_side != "MIXED":
            strong_streak += 1
        else:
            strong_streak = 1
            prev_strong_side = strong_side

        def side_text(side_name, info):
            side = side_name.lower()
            notes = [info["label"]]
            if state_streak[side] >= 3 and info["state"] != "MIXED":
                notes.append(f"consistency: same {info['state'].lower()} for {state_streak[side]} snapshots")
            elif info["state"] != "MIXED":
                notes.append("consistency: early, needs more snapshots")
            if info["long_build"] and info["short_cover"]:
                notes.append(f"fresh build {info['long_build']} vs covering {info['short_cover']}")
            if info["avg_p"] > 0 and info["avg_v"] < 0:
                notes.append("price up but volume down = short covering, not fresh long")
            if info["avg_p"] < 0 and info["avg_v"] < 0:
                notes.append("price+volume down = unwinding/exit")
            if side == "ce" and info["state"] in ("LONG_BUILD", "SLOW_ACCUM") and not pe_has_unwind:
                notes.append("opposite PE unwind missing")
            if side == "pe" and info["state"] in ("LONG_BUILD", "SLOW_ACCUM") and not ce_has_unwind:
                notes.append("opposite CE unwind missing")
            return "; ".join(notes[:4])

        final_side = strong_side

        if strong_side == "PE":
            final = "PE stronger than CE from current vs past snapshot context; bearish pressure"
        elif strong_side == "CE":
            final = "CE stronger than PE from current vs past snapshot context; bullish pressure"
        elif ce_has_unwind and (pe_has_build or pe["avg_p"] > 0 or pe["delta_up"] >= 3):
            final_side = "PE"
            final = "CE unwinding while PE is improving; bearish pressure, PE side favored"
        elif pe_has_unwind and (ce_has_build or ce["avg_p"] > 0 or ce["delta_up"] >= 3):
            final_side = "CE"
            final = "PE unwinding while CE is improving; bullish pressure, CE side favored"
        elif ce_has_build and not pe_has_unwind:
            final = "CE build seen, but PE not unwinding; do not mark CE stronger yet"
        elif pe_has_build and not ce_has_unwind:
            final = "PE build seen, but CE not unwinding; do not mark PE stronger yet"
        else:
            final = "mixed/no clear side; wait for handoff"

        if strong_side != "MIXED":
            if strong_streak >= 3:
                final += f"; verdict consistency {strong_streak} snapshots"
            else:
                final += "; verdict early"
        if ce["state"] == "UNWINDING":
            final += "; CE unwinding"
        if pe["state"] == "UNWINDING":
            final += "; PE unwinding"

        pe_text = side_text("PE", pe)
        ce_text = side_text("CE", ce)
        analysis[ts] = {
            "pe": pe_text,
            "ce": ce_text,
            "final": final,
            "final_side": final_side,
            "pe_points": analysis_points(pe_text),
            "ce_points": analysis_points(ce_text),
            "final_points": analysis_points(final),
        }

    return analysis

def print_snapshot_analysis(ts, snapshot_analysis):
    info = snapshot_analysis.get(ts)
    if not info:
        return
    print(f"  {bold('SNAPSHOT ANALYSIS')} {dim(str(ts)[:19])}")
    print(f"    {red('PE side:')} {info['pe']}")
    print(f"    {green('CE side:')} {info['ce']}")
    print(f"    {yellow('Final:')} {info['final']}")

def analysis_points(text, max_points=2):
    points = [p.strip() for p in str(text).split(";") if p.strip()]
    return points[:max_points] or ["mixed/no clear side"]

def _compact_note(text):
    text = str(text).strip()
    compact_map = (
        ("mixed/no clear build", "mixed/no clear"),
        ("fresh long build", "fresh build"),
        ("short covering", "short covering"),
        ("unwinding/buyers exiting", "unwinding/exit"),
        ("price up but volume down = short covering, not fresh long", "price up, vol down"),
        ("price+volume down = unwinding/exit", "price+vol down"),
        ("consistency: same", "consistent"),
        ("consistency: early, needs more snapshots", "early, need confirm"),
        ("consistency: needs more snapshots", "need confirm"),
        ("opposite PE unwind missing", "PE unwind missing"),
        ("opposite CE unwind missing", "CE unwind missing"),
        ("PE stronger than CE from current vs past snapshot context", "PE stronger vs CE"),
        ("CE stronger than PE from current vs past snapshot context", "CE stronger vs PE"),
        ("bearish pressure", "bearish pressure"),
        ("bullish pressure", "bullish pressure"),
        ("wait for handoff", "wait handoff"),
    )
    for old, new in compact_map:
        if text.startswith(old):
            text = text.replace(old, new, 1)
            break
    if text.startswith("mixed/no clear") and "(" in text:
        text = text.split("(", 1)[0].strip()
    return text

def _wrap_words(text, width):
    text = str(text).strip()
    if not text:
        return [""]
    words = text.split()
    rows = []
    current = ""
    for word in words:
        if len(word) > width:
            if current:
                rows.append(current)
                current = ""
            while len(word) > width:
                rows.append(word[:width])
                word = word[width:]
            if word:
                current = word
            continue
        candidate = word if not current else current + " " + word
        if len(candidate) <= width:
            current = candidate
        else:
            rows.append(current)
            current = word
    if current:
        rows.append(current)
    return rows

def _point_rows(number, text, width):
    text = _compact_note(text)
    prefix = f"{number}. "
    if "(" in text and text.endswith(")"):
        main, detail = text.split("(", 1)
        rows = []
        for idx, part in enumerate(_wrap_words(main.strip(), width - len(prefix))):
            rows.append((prefix if idx == 0 else "   ") + part)
        for part in _wrap_words("(" + detail.strip(), width - 3):
            rows.append("   " + part)
        return rows
    rows = []
    for idx, part in enumerate(_wrap_words(text, width - len(prefix))):
        rows.append((prefix if idx == 0 else "   ") + part)
    return rows

def snapshot_analysis_column(ts, snapshot_analysis, line_no, width=24):
    info = snapshot_analysis.get(ts)
    if not info:
        return ""

    pe_points = info.get("pe_points") or analysis_points(info.get("pe", ""))
    ce_points = info.get("ce_points") or analysis_points(info.get("ce", ""))
    final_points = info.get("final_points") or analysis_points(info.get("final", ""))

    final_side = info.get("final_side")
    final_color = red if final_side == "PE" else green if final_side == "CE" else yellow

    panel = []
    panel.append((red, "PE side:"))
    for idx, point in enumerate(pe_points[:2], 1):
        panel.extend((red, row) for row in _point_rows(idx, point, width))

    panel.append((green, "CE side:"))
    for idx, point in enumerate(ce_points[:2], 1):
        panel.extend((green, row) for row in _point_rows(idx, point, width))

    panel.append((final_color, "Final:"))
    for idx, point in enumerate(final_points[:2], 1):
        panel.extend((final_color, row) for row in _point_rows(idx, point, width))

    if final_side in ("PE", "CE"):
        direction = "downside bias" if final_side == "PE" else "upside bias"
        panel.append((final_color, "Key: " + direction))

    if 1 <= line_no <= len(panel):
        color, text = panel[line_no - 1]
        return color(text)
    return ""


def pct_change_col(series):
    return (series.pct_change(fill_method=None) * 100).round(2)

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
def run_single_analysis(csv_path=None, analysis_date=None):
    csv_path = csv_path or CSV_PATH
    analysis_date = analysis_date or ANALYSIS_DATE

    csv = Path(csv_path)
    if not csv.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}\nRun 1_db_to_csv.py first.")

    print(bold(cyan(f"\n  Loading {csv_path} …")))
    df = pd.read_csv(csv, parse_dates=["timestamp"])
    print("CSV date range:", df["timestamp"].min(), "to", df["timestamp"].max())


    # Keep only selected date from the CSV
    # Keep only selected date from the CSV
    df = df[df["timestamp"].dt.date == pd.to_datetime(analysis_date).date()].copy()
    df.reset_index(drop=True, inplace=True)

    # Stop script clearly if selected date is not available in CSV
    if df.empty:
        print(red(f"No rows found for ANALYSIS_DATE = {analysis_date}"))
        print(yellow("Use one date from Available dates printed above."))
        return {
            "csv": Path(csv_path).name,
            "date": str(analysis_date),
            "trades": 0,
            "profit_count": 0,
            "loss_count": 0,
            "flat_count": 0,
            "total_pnl": 0.0,
            "best_move_pnl": 0.0,
            "bad_move_pnl": 0.0,
            "trade_details": [],
        }

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
            # Display-only OI buildup row:
            # Big moves can start with option price + volume expansion before
            # delta/gamma ranks become strong. Keep these candles visible in
            # the OI buildup table for breakdowns like 2024-01-02 09:54-10:00.
            sdf[f"{side}_price_volume_build"] = (
                (sdf[f"{side}_p_pct"] >= OI_TABLE_PRICE_PCT) &
                (sdf[f"{side}_v_pct"] >= OI_TABLE_VOLUME_PCT)
            )
            # Also keep the opposite-side weakness visible. During a PE move,
            # CE rows often have price falling and should be shown as weakness
            # context instead of disappearing from the table.
            sdf[f"{side}_price_drop_weakness"] = (
                sdf[f"{side}_p_pct"] <= OI_TABLE_PRICE_DROP_PCT
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

    if not records:
        print(yellow(f"No usable option rows after filters for ANALYSIS_DATE = {analysis_date}"))
        return {
            "csv": Path(csv_path).name,
            "date": str(analysis_date),
            "trades": 0,
            "profit_count": 0,
            "loss_count": 0,
            "flat_count": 0,
            "total_pnl": 0.0,
            "best_move_pnl": 0.0,
            "bad_move_pnl": 0.0,
            "trade_details": [],
        }

    full       = pd.concat(records, ignore_index=True).sort_values(["timestamp","strike"])
    full       = attach_nifty_200ma(full)
    snapshot_analysis = build_snapshot_analysis(full)
    timestamps = sorted(full["timestamp"].unique())

    W  = 177   # console width - wide enough for all columns plus compact snapshot analysis
    W3 = W + STRIKES_NEARBY * 14

    # ══════════════════════════════════════════════════════════════════════════
    # LAYER 1 — SAME-CANDLE SPIKE REPORT
    # ══════════════════════════════════════════════════════════════════════════
    header("SNAPSHOT OI BUILDUP — every timestamp, CE first then PE", W)
    print(f"  {dim('Layer 1 threshold: runtime percentile ≥')} {bold(str(STRENGTH_PCT))}th\n")

    print(
        f"  {dim('Also showing price-volume buildup rows: P% >=')} "
        f"{bold(str(OI_TABLE_PRICE_PCT))}   {dim('V% >=')} "
        f"{bold(str(OI_TABLE_VOLUME_PCT))}   "
        f"{dim('and weakness rows: P% <=')} {bold(str(OI_TABLE_PRICE_DROP_PCT))}\n"
    )

    h1 = (f"  {'TIMESTAMP':<19}  {'STRIKE':>8}  {'SPOT':>8}  {'SIDE':>4}  "
          f"{'SCORE':>5}  {'STRENGTH':>18}  "
          f"{'DELTA':>10} {'D CHG%':>9}  {'GAMMA':>10} {'G CHG%':>9}  "
          f"{'VOLUME':>10} {'V%':>9}  {'PRICE':>8} {'P%':>9}  {'IV':>7}  {'ANALYSIS':<24}")
    print(bold(h1))
    sep(W)
    
    
    snapshot_rows = []
    layer1_rows = []
    for side in sides:
        for _, r in full.iterrows():
            snapshot_rows.append((r["timestamp"], r["strike"], r["spot"], side,
                                  r[f"{side}_score"],
                                  r[col_map[side]["delta"]], r[f"{side}_d_pct"],
                                  r[col_map[side]["gamma"]], r[f"{side}_g_pct"],
                                  r[col_map[side]["volume"]],r[f"{side}_v_pct"],
                                  r[col_map[side]["price"]], r[f"{side}_p_pct"],
                                  r[col_map[side]["iv"]]))

        sub = full[
            full[f"{side}_same_spike"] |
            full[f"{side}_price_volume_build"] |
            full[f"{side}_price_drop_weakness"]
        ].copy()
        for _, r in sub.iterrows():
            layer1_rows.append((r["timestamp"], r["strike"], r["spot"], side,
                                r[f"{side}_score"],
                                r[col_map[side]["delta"]], r[f"{side}_d_pct"],
                                r[col_map[side]["gamma"]], r[f"{side}_g_pct"],
                                r[col_map[side]["volume"]],r[f"{side}_v_pct"],
                                r[col_map[side]["price"]], r[f"{side}_p_pct"],
                                r[col_map[side]["iv"]]))

    # Same timestamp → all CE first → all PE next
    snapshot_rows.sort(key=lambda x: (x[0], 0 if x[3] == "ce" else 1, x[1]))
    layer1_rows.sort(key=lambda x: (x[0], 0 if x[3] == "ce" else 1, x[1]))

    prev_snapshot_ts = None
    snapshot_line_no = 0
    for ts, stk, spot, side, score, dv, dp, gv, gp, vv, vp, pv, pp, iv in snapshot_rows:
        is_first_snapshot_row = ts != prev_snapshot_ts
        if prev_snapshot_ts is not None and ts != prev_snapshot_ts:
            print()
            snapshot_line_no = 0
        prev_snapshot_ts = ts
        snapshot_line_no += 1
        analysis_txt = snapshot_analysis_column(ts, snapshot_analysis, snapshot_line_no)

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
            f"{dim(f'{iv:>7.2f}%')}  {analysis_txt:<24}"
        )

    if not snapshot_rows:
        print(f"  {dim('No snapshot rows found.')}")
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
    weak_momentum_override_reject = 0
    entry_start_reject = 0
    early_entry_accept_count = 0
    low_flow_reject = 0
    low_same_side_reject = 0
    late_flow_reject = 0
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

        flow_score, same_side_count, opp_side_count, flow_reason = get_flow_confirm(
            full, ts, stk, side
        )
        early_entry_ok = early_oi_entry_ok(
            ts, side, pp, vp, flow_score, same_side_count, opp_side_count, flow_reason
        )

        if ts.time() < ENTRY_START and not early_entry_ok:
            entry_start_reject += 1
            continue

        if early_entry_ok:
            early_entry_accept_count += 1

        ma_ok, ma_reason = passes_nifty_200ma_filter(r, side)
        if ma_reason == "MA missing":
            ma_missing_count += 1
        if not ma_ok and not (momentum_ok or early_entry_ok):
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
        if not chop_ok and not (momentum_ok or early_entry_ok):
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

        # Price momentum can override 200MA/chop only when the option move is
        # supported by nearby strikes. This avoids one-candle P% spikes that
        # show high price momentum but later produce tiny BEST and deep BAD.
        momentum_override_used = momentum_ok and (not ma_ok or not chop_ok)
        if STRICT_MOMENTUM_OVERRIDE_QUALITY and momentum_override_used and not early_entry_ok:
            momentum_quality_ok = (
                flow_score >= MOMENTUM_OVERRIDE_MIN_FLOW and
                same_side_count >= MOMENTUM_OVERRIDE_MIN_SAME_SIDE and
                opp_side_count >= MOMENTUM_OVERRIDE_MIN_OPP_SUPPORT and
                momentum_override_slope_ok(r, side)
            )
            if not momentum_quality_ok:
                weak_momentum_override_reject += 1
                continue

        if side == "ce":
            delta_ok = dp > 3
        else:
            delta_ok = dp > 3

        price_ok = pp > 1
        volume_ok = vp > 30
        flow_ok = flow_score >= MIN_ENTRY_FLOW_SCORE

        if ts.time() >= LATE_ENTRY_START and flow_score < LATE_ENTRY_MIN_FLOW:
            late_flow_reject += 1
            continue

        strong_checks = [
            delta_ok,
            volume_ok,
            price_ok,
            flow_ok
        ]

        if side == "pe" and not flow_ok:
            pe_flow_reject += 1

        if not flow_ok:
            low_flow_reject += 1

        same_side_ok = same_side_entry_ok(side, same_side_count, opp_side_count, flow_reason)

        if not same_side_ok:
            low_same_side_reject += 1

        if sum(strong_checks) >= 3 and same_side_ok:

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
                full,
                ts,
                stk,
                side,
                entry_price,
                col_map,
                momentum_entry=momentum_ok,
                flow_score=flow_score,
                same_side_count=same_side_count,
                opp_side_count=opp_side_count,
            )

            entry_price = pv
            pnl_points = exit_price - entry_price if exit_price is not None else np.nan

            best_move, best_time, best_price = compute_strike_best_move(
                full, ts, stk, side, entry_price, col_map
            )
            bad_move, bad_time, bad_price = compute_strike_bad_move(
                full, ts, stk, side, entry_price, col_map
            )

            top_rows.append((
            ts, stk, spot, side,
            entry_price, exit_ts, exit_price, pnl_points,
            best_move, best_time, best_price,
            bad_move, bad_time, bad_price,
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
            f"{momentum_reason if momentum_ok else ''} "
            f"{'EARLY_OI' if early_entry_ok else ''} {flow_reason}"
            ))
        
        else:
            if side == "pe":
                pe_strength_reject += 1 

    # First sort by ENTRY SCORE so duplicate same-time signals keep the strongest row.
    top_rows.sort(key=lambda x: x[14], reverse=True)

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
    daily_loss_reentry_skip_count = 0

    if not ALLOW_OVERLAPPING_TRADES:
        single_trade_rows = []
        active_until = None
        daily_loss_count = {}

        for r in unique_rows:
            entry_ts = r[0]
            exit_ts = r[5]
            pnl_points = r[7]
            trade_day = entry_ts.date()

            if active_until is not None and entry_ts < active_until:
                overlapping_skip_count += 1
                continue

            if (
                daily_loss_count.get(trade_day, 0) >= DAILY_LOSS_LIMIT and
                entry_ts.time() >= DAILY_LOSS_CUTOFF
            ):
                daily_loss_reentry_skip_count += 1
                continue

            single_trade_rows.append(r)
            active_until = exit_ts if exit_ts is not None and not pd.isna(exit_ts) else entry_ts
            if pnl_points is not None and not pd.isna(pnl_points) and float(pnl_points) < 0:
                daily_loss_count[trade_day] = daily_loss_count.get(trade_day, 0) + 1

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
              f"{dim('MA/chop overrides used:')} {bold(str(momentum_override_count))}   "
              f"{dim('Weak overrides blocked:')} {bold(str(weak_momentum_override_reject))}")
    else:
        print(f"  {dim('Price momentum override:')} {bold('OFF')}")
    print(f"  {dim('Entry quality filters:')} {bold('ON')}   "
          f"{dim('Start >=')} {bold(ENTRY_START.strftime('%H:%M'))}   "
          f"{dim('Flow >=')} {bold(str(MIN_ENTRY_FLOW_SCORE))}   "
          f"{dim('Same-side >=')} {bold(str(MIN_SAME_SIDE_COUNT))}   "
          f"{dim('Open blocked:')} {bold(str(entry_start_reject))}   "
          f"{dim('Low flow blocked:')} {bold(str(low_flow_reject))}   "
          f"{dim('Low same-side blocked:')} {bold(str(low_same_side_reject))}   "
          f"{dim('Late low-flow blocked:')} {bold(str(late_flow_reject))}")
    if USE_EARLY_OI_ENTRY:
        print(f"  {dim('Early OI entry:')} {bold('ON')}   "
              f"{dim('Window:')} {bold(EARLY_ENTRY_START.strftime('%H:%M') + '-' + ENTRY_START.strftime('%H:%M'))}   "
              f"{dim('Flow >=')} {bold(str(EARLY_ENTRY_MIN_FLOW))}   "
              f"{dim('Same/Opp >=')} {bold(str(EARLY_ENTRY_MIN_SAME_SIDE) + '/' + str(EARLY_ENTRY_MIN_OPP_SUPPORT))}   "
              f"{dim('P% >=')} {bold(str(EARLY_ENTRY_MIN_PRICE_PCT))}   "
              f"{dim('V% >=')} {bold(str(EARLY_ENTRY_MIN_VOLUME_PCT))}   "
              f"{dim('Cross confirm:')} {bold('ON' if EARLY_REQUIRE_CROSS_CONFIRM else 'OFF')}   "
              f"{dim('Accepted:')} {bold(str(early_entry_accept_count))}")
    else:
        print(f"  {dim('Early OI entry:')} {bold('OFF')}")
    if ALLOW_OVERLAPPING_TRADES:
        print(f"  {dim('Single active trade rule:')} {bold('OFF')}   "
              f"{dim('Overlapping entries allowed')}")
    else:
        print(f"  {dim('Single active trade rule:')} {bold('ON')}   "
              f"{dim('Overlapping entries skipped:')} {bold(str(overlapping_skip_count))}   "
              f"{dim('Daily loss re-entry skipped:')} {bold(str(daily_loss_reentry_skip_count))}")
    print()

    h_top = (
        f"  {'ENTRY TIME':<19}  {'EXIT TIME':<19}  {'STRIKE':>8}  {'SPOT':>8}  {'SIDE':>4}  "
        f"{'ENTRY':>8}  {'EXIT':>8}  {'PNL':>8}  {'BEST MOVE':>10}  {'BAD MOVE':>9}  {'BEST TIME':<19}  "
        f"{'ENTRY SCR':>9}  {'SYS SCR':>7}  "
        f"{'D%':>9}  {'G%':>9}  {'V%':>9}  {'P%':>9}  {'EXIT REASON':<28}"
    )
    print(bold(h_top))
    sep(W)

    for ts, stk, spot, side, entry_price, exit_ts, exit_price, pnl_points, best_move, best_time, best_price, bad_move, bad_time, bad_price, entry_score, sys_score, dp, gp, vp, pp, exit_reason, reason in unique_rows[:TOP_N]:
        side_c = bright_green("CE") if side == "ce" else bright_red("PE")

        pnl_txt = bright_green(f"{pnl_points:>8.2f}") if pnl_points >= 0 else bright_red(f"{pnl_points:>8.2f}")
        best_txt = bright_green(f"{best_move:>10.2f}") if best_move >= 0 else bright_red(f"{best_move:>10.2f}")
        bad_txt = bright_green(f"{bad_move:>9.2f}") if bad_move >= 0 else bright_red(f"{bad_move:>9.2f}")

        print(
            f"  {dim(str(ts)[:19])}  "
            f"{dim(str(exit_ts)[:19])}  "
            f"{cyan(f'{stk:>8.1f}')}  {cyan(f'{spot:>8.2f}')}  {side_c}  "
            f"{entry_price:>8.2f}  {exit_price:>8.2f}  {pnl_txt}  {best_txt}  {bad_txt}  "
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

        for ts, stk, spot, side, entry_price, exit_ts, exit_price, pnl_points, best_move, best_time, best_price, bad_move, bad_time, bad_price, entry_score, sys_score, dp, gp, vp, pp, exit_reason, reason in pe_rows[:TOP_N]:
            side_c = bright_red("PE")

            pnl_txt = bright_green(f"{pnl_points:>8.2f}") if pnl_points >= 0 else bright_red(f"{pnl_points:>8.2f}")
            best_txt = bright_green(f"{best_move:>10.2f}") if best_move >= 0 else bright_red(f"{best_move:>10.2f}")
            bad_txt = bright_green(f"{bad_move:>9.2f}") if bad_move >= 0 else bright_red(f"{bad_move:>9.2f}")

            print(
                f"  {dim(str(ts)[:19])}  "
                f"{dim(str(exit_ts)[:19])}  "
                f"{cyan(f'{stk:>8.1f}')}  {cyan(f'{spot:>8.2f}')}  {side_c}  "
                f"{entry_price:>8.2f}  {exit_price:>8.2f}  {pnl_txt}  {best_txt}  {bad_txt}  "
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

    trade_details = []
    for r in unique_rows:
        ts, stk, spot, side, entry_price, exit_ts, exit_price, pnl_points, best_move, best_time, best_price, bad_move, bad_time, bad_price, entry_score, sys_score, dp, gp, vp, pp, exit_reason, reason = r
        trade_details.append({
            "entry_time": str(ts)[:19],
            "exit_time": str(exit_ts)[:19],
            "side": side.upper(),
            "strike": float(stk),
            "entry": float(entry_price),
            "exit": float(exit_price),
            "pnl": float(pnl_points),
            "best_move": float(best_move),
            "best_time": str(best_time)[:19],
            "bad_move": float(bad_move),
            "bad_time": str(bad_time)[:19],
            "entry_score": float(entry_score),
            "sys_score": float(sys_score),
            "d_pct": float(dp),
            "g_pct": float(gp),
            "v_pct": float(vp),
            "p_pct": float(pp),
            "exit_reason": str(exit_reason),
        })

    return {
        "csv": Path(csv_path).name,
        "date": str(analysis_date),
        "trades": len(option_pnls),
        "profit_count": profit_count,
        "loss_count": loss_count,
        "flat_count": flat_count,
        "total_pnl": total_option_pnl,
        "best_move_pnl": round(sum(float(r[8]) for r in unique_rows if r[8] is not None and not pd.isna(r[8])), 2),
        "bad_move_pnl": round(sum(float(r[11]) for r in unique_rows if r[11] is not None and not pd.isna(r[11])), 2),
        "trade_details": trade_details,
    }

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Options flow strength analyser. No args keeps hardcoded CSV/date "
            "full-output mode. --monthly enables compact date-by-date summary mode."
        )
    )
    parser.add_argument("--csv", "--csv-path", dest="csv_path",
                        help="Run one CSV file instead of hardcoded CSV_PATH.")
    parser.add_argument("--date", "--analysis-date", dest="analysis_date",
                        help="Run one date instead of hardcoded ANALYSIS_DATE.")
    parser.add_argument("--monthly", action="store_true",
                        help="Compact mode: run weekly expiry CSVs for a selected month/year.")
    parser.add_argument("--month",
                        help="Month name or number for --monthly, e.g. jan, january, 1.")
    parser.add_argument("--year", type=int,
                        help="Year for --monthly, e.g. 2024.")
    parser.add_argument("--csv-dir", default=str(Path(__file__).resolve().parent),
                        help="Folder containing weekly oi_YYYY_MM_DD.csv files.")
    parser.add_argument("--no-next-week", action="store_true",
                        help="Monthly mode: do not include first 7 days of next month.")
    parser.add_argument("--entry-start", type=parse_time_arg,
                        help="Normal entry start time, HH:MM. Default from USER CONFIG: 09:45.")
    parser.add_argument("--flow", "--min-flow", dest="min_flow", type=int,
                        help="Minimum entry FLOW score. Default from USER CONFIG: 10.")
    parser.add_argument("--same-side", "--min-same-side", dest="min_same_side", type=int,
                        help="Minimum same-side confirming strikes. Default from USER CONFIG: 2.")
    parser.add_argument("--late-start", type=parse_time_arg,
                        help="Late-entry stricter flow start time, HH:MM. Default: 14:15.")
    parser.add_argument("--late-flow", type=int,
                        help="Minimum FLOW after --late-start. Default: 12.")
    parser.add_argument("--early-entry", action="store_true",
                        help="Enable 09:25-09:45 super-strong OI buildup entries.")
    parser.add_argument("--early-start", type=parse_time_arg,
                        help="Early OI entry start time, HH:MM. Default: 09:25.")
    parser.add_argument("--early-flow", type=int,
                        help="Minimum FLOW for early OI entries. Default: 16.")
    parser.add_argument("--early-same-side", type=int,
                        help="Minimum same-side strikes for early OI entries. Default: 3.")
    parser.add_argument("--early-opp", type=int,
                        help="Minimum opposite-side support strikes for early OI entries. Default: 2.")
    parser.add_argument("--early-price-pct", type=float,
                        help="Minimum option price %% for early OI entries. Default: 6.")
    parser.add_argument("--early-volume-pct", type=float,
                        help="Minimum option volume %% for early OI entries. Default: 40.")
    parser.add_argument("--early-no-cross-confirm", action="store_true",
                        help="Early entries can use strong same-side flow even without OI_BULL/OI_BEAR.")
    parser.add_argument("--no-relax-cross-side", action="store_true",
                        help="Disable relaxed same-side rule when OI_BULL/OI_BEAR has opposite-side support.")
    return parser.parse_args()

def apply_arg_config(args):
    global ENTRY_START, MIN_ENTRY_FLOW_SCORE, MIN_SAME_SIDE_COUNT
    global LATE_ENTRY_START, LATE_ENTRY_MIN_FLOW
    global USE_EARLY_OI_ENTRY, EARLY_ENTRY_START, EARLY_ENTRY_MIN_FLOW
    global EARLY_ENTRY_MIN_SAME_SIDE, EARLY_ENTRY_MIN_OPP_SUPPORT
    global EARLY_ENTRY_MIN_PRICE_PCT, EARLY_ENTRY_MIN_VOLUME_PCT
    global EARLY_REQUIRE_CROSS_CONFIRM
    global RELAX_SAME_SIDE_ON_CROSS_CONFIRM

    if args.entry_start is not None:
        ENTRY_START = args.entry_start
    if args.min_flow is not None:
        MIN_ENTRY_FLOW_SCORE = args.min_flow
    if args.min_same_side is not None:
        MIN_SAME_SIDE_COUNT = args.min_same_side
    if args.late_start is not None:
        LATE_ENTRY_START = args.late_start
    if args.late_flow is not None:
        LATE_ENTRY_MIN_FLOW = args.late_flow

    if args.early_entry:
        USE_EARLY_OI_ENTRY = True
    if args.early_start is not None:
        EARLY_ENTRY_START = args.early_start
    if args.early_flow is not None:
        EARLY_ENTRY_MIN_FLOW = args.early_flow
    if args.early_same_side is not None:
        EARLY_ENTRY_MIN_SAME_SIDE = args.early_same_side
    if args.early_opp is not None:
        EARLY_ENTRY_MIN_OPP_SUPPORT = args.early_opp
    if args.early_price_pct is not None:
        EARLY_ENTRY_MIN_PRICE_PCT = args.early_price_pct
    if args.early_volume_pct is not None:
        EARLY_ENTRY_MIN_VOLUME_PCT = args.early_volume_pct
    if args.early_no_cross_confirm:
        EARLY_REQUIRE_CROSS_CONFIRM = False
    if args.no_relax_cross_side:
        RELAX_SAME_SIDE_ON_CROSS_CONFIRM = False

def print_compact_monthly_summary(results, month, year, start_date, end_date):
    header(f"MONTHLY SUMMARY - {month_name(month)} {year}", 112)
    print(f"  Date range: {start_date} to {end_date}")
    print(f"  {'CSV FILE':<20} {'DATE':<10} {'TRADES':>6} {'PROFIT':>6} {'LOSS':>6} {'FLAT':>5} {'PNL':>10} {'BEST MOVE':>10} {'BAD MOVE':>10}")
    sep(112)

    total_trades = 0
    total_profit = 0
    total_loss = 0
    total_flat = 0
    total_pnl = 0.0
    total_best = 0.0
    total_bad = 0.0

    for r in results:
        pnl_txt = bright_green(f"{r['total_pnl']:>10.2f}") if r["total_pnl"] >= 0 else bright_red(f"{r['total_pnl']:>10.2f}")
        best_txt = bright_green(f"{r['best_move_pnl']:>10.2f}") if r["best_move_pnl"] >= 0 else bright_red(f"{r['best_move_pnl']:>10.2f}")
        bad_txt = bright_green(f"{r['bad_move_pnl']:>10.2f}") if r["bad_move_pnl"] >= 0 else bright_red(f"{r['bad_move_pnl']:>10.2f}")
        print(f"  {r['csv']:<20} {r['date']:<10} {r['trades']:>6} {r['profit_count']:>6} "
              f"{r['loss_count']:>6} {r['flat_count']:>5} {pnl_txt} {best_txt} {bad_txt}")

        if r.get("trade_details"):
            print(f"    {'ENTRY TIME':<19} {'EXIT TIME':<19} {'SIDE':<4} {'STRIKE':>8} "
                  f"{'ENTRY':>8} {'EXIT':>8} {'PNL':>9} {'BEST':>9} {'BAD':>9} {'BEST TIME':<19} "
                  f"{'D%':>8} {'G%':>8} {'V%':>8} {'P%':>8}  EXIT REASON")
            for t in r["trade_details"]:
                trade_pnl = bright_green(f"{t['pnl']:>9.2f}") if t["pnl"] >= 0 else bright_red(f"{t['pnl']:>9.2f}")
                trade_best = bright_green(f"{t['best_move']:>9.2f}") if t["best_move"] >= 0 else bright_red(f"{t['best_move']:>9.2f}")
                trade_bad = bright_green(f"{t['bad_move']:>9.2f}") if t["bad_move"] >= 0 else bright_red(f"{t['bad_move']:>9.2f}")
                print(f"    {t['entry_time']:<19} {t['exit_time']:<19} {t['side']:<4} "
                      f"{t['strike']:>8.1f} {t['entry']:>8.2f} {t['exit']:>8.2f} "
                      f"{trade_pnl} {trade_best} {trade_bad} {t['best_time']:<19} "
                      f"{t['d_pct']:>7.2f}% {t['g_pct']:>7.2f}% {t['v_pct']:>7.2f}% "
                      f"{t['p_pct']:>7.2f}%  {t['exit_reason']}")
            print()

        total_trades += r["trades"]
        total_profit += r["profit_count"]
        total_loss += r["loss_count"]
        total_flat += r["flat_count"]
        total_pnl += r["total_pnl"]
        total_best += r["best_move_pnl"]
        total_bad += r["bad_move_pnl"]

    sep(112)
    total_pnl_txt = bright_green(f"{total_pnl:>10.2f}") if total_pnl >= 0 else bright_red(f"{total_pnl:>10.2f}")
    total_best_txt = bright_green(f"{total_best:>10.2f}") if total_best >= 0 else bright_red(f"{total_best:>10.2f}")
    total_bad_txt = bright_green(f"{total_bad:>10.2f}") if total_bad >= 0 else bright_red(f"{total_bad:>10.2f}")
    print(f"  {'TOTAL':<20} {'':<10} {total_trades:>6} {total_profit:>6} {total_loss:>6} "
          f"{total_flat:>5} {total_pnl_txt} {total_best_txt} {total_bad_txt}")
    print()

def run_monthly(args):
    if not args.month or not args.year:
        raise SystemExit("--monthly needs both --month and --year")

    month = parse_month(args.month)
    start_date, end_date = monthly_date_range(
        args.year,
        month,
        include_next_week=not args.no_next_week,
    )

    csv_dir = Path(args.csv_dir)
    date_to_csv = {}
    for csv_file in sorted(csv_dir.glob("oi_*.csv")):
        file_date = date_from_oi_filename(csv_file)
        if not file_date:
            continue

        # A month-end trading date can live inside the next weekly expiry CSV.
        # Scan one extra week of expiry files, but only keep trading dates that
        # are inside the requested monthly date range.
        if file_date < start_date or file_date > (pd.Timestamp(end_date) + pd.Timedelta(days=7)).date():
            continue

        for trade_date in trading_dates_in_csv(csv_file):
            if not (start_date <= trade_date <= end_date):
                continue
            current = date_to_csv.get(trade_date)
            if current is None:
                date_to_csv[trade_date] = (csv_file, file_date)
                continue
            _, current_file_date = current
            if file_date >= trade_date and (current_file_date < trade_date or file_date < current_file_date):
                date_to_csv[trade_date] = (csv_file, file_date)

    csv_files = [(csv_file, trade_date) for trade_date, (csv_file, _) in sorted(date_to_csv.items())]

    if not csv_files:
        print(red(f"No trading dates found in {csv_dir} for {start_date} to {end_date}"))
        return []

    results = []
    for csv_file, trade_date in csv_files:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = run_single_analysis(str(csv_file), str(trade_date))
        results.append(result)

    print_compact_monthly_summary(results, month, args.year, start_date, end_date)
    return results

def main():
    if len(sys.argv) == 1:
        run_single_analysis()
        return

    args = parse_args()
    apply_arg_config(args)
    if args.monthly:
        run_monthly(args)
        return

    run_single_analysis(args.csv_path or CSV_PATH, args.analysis_date or ANALYSIS_DATE)


if __name__ == "__main__":
    main()
