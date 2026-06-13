"""
Delta/Gamma Spike Finder — reads from SQLite oi_*.db files
=============================================================
Usage:
  python spike_finder_db.py --oi-db "C:\\path\\to\\OIDATA" --from-date 2026-06-01
  python spike_finder_db.py --oi-db "C:\\path\\to\\oi_2026_06_01.db"   (single file)

Finds, per strike (ATM ±100 only, both CE & PE):
  - Same-bar spikes: delta AND gamma both change >=THRESH% in one interval
  - Cross-interval: delta spikes one bar, gamma spikes the NEXT bar (and vice versa)

Output is printed date-by-date.
"""
from __future__ import annotations

import sqlite3
import argparse
import re
import sys
from pathlib import Path

import pandas as pd

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

THRESH = 10.0  # % change threshold

STRATEGY3_DIR = Path(
    r"C:\Users\Vidya sagar\OneDrive\Desktop\myscripts\StrategyBuilder\Strategy3MAGreeks"
)
DEFAULT_NIFTY_EXCEL = Path(
    r"C:\Users\Vidya sagar\OneDrive\Desktop\myscripts\StrategyBuilder\nifty50database\nifty_live_all_timeframes.xlsx"
)


def pct(curr, prev):
    if prev == 0 or pd.isna(prev) or pd.isna(curr):
        return 0.0
    return ((curr - prev) / abs(prev)) * 100.0


def nearest_atm(spot):
    return int(round(spot / 50) * 50)


def load_oi_db(path: str | Path) -> pd.DataFrame:
    with sqlite3.connect(path) as conn:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(oi_snapshots)").fetchall()}
        expiry = "expiry" if "expiry" in cols else "'' AS expiry"
        df = pd.read_sql_query(f"""
            SELECT timestamp, strike, spot, {expiry},
                   call_delta, put_delta, call_gamma, put_gamma
            FROM oi_snapshots ORDER BY timestamp, strike
        """, conn)
    df["timestamp"] = pd.to_datetime(df["timestamp"], format="mixed", errors="coerce")
    for c in ["strike", "spot", "call_delta", "put_delta", "call_gamma", "put_gamma"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df = df.dropna(subset=["timestamp"])
    return df.drop_duplicates(subset=["timestamp", "strike"], keep="last") \
             .sort_values(["timestamp", "strike"]).reset_index(drop=True)


def _date_from_filename(path: Path):
    m = re.search(r"(\d{4}_\d{2}_\d{2})", path.stem)
    if not m:
        return None
    return pd.Timestamp(m.group(1).replace("_", "-")).date()


def analyze(df: pd.DataFrame, side: str) -> pd.DataFrame:
    delta_col = f"{side}_delta"
    gamma_col = f"{side}_gamma"

    rows = []
    for strike, g in df.groupby("strike"):
        g = g.sort_values("timestamp").reset_index(drop=True)
        g["delta_pct"] = [0.0] + [pct(abs(g[delta_col].iloc[i]), abs(g[delta_col].iloc[i-1])) for i in range(1, len(g))]
        g["gamma_pct"] = [0.0] + [pct(g[gamma_col].iloc[i], g[gamma_col].iloc[i-1]) for i in range(1, len(g))]
        g["delta_spike"] = g["delta_pct"] >= THRESH
        g["gamma_spike"] = g["gamma_pct"] >= THRESH
        g["strike"] = strike
        rows.append(g)

    return pd.concat(rows, ignore_index=True) if rows else df.iloc[0:0]


def filter_near_atm(df: pd.DataFrame) -> pd.DataFrame:
    keep = []
    for ts, g in df.groupby("timestamp"):
        spot = g["spot"].iloc[0]
        atm = nearest_atm(spot)
        allowed = {atm - 100, atm - 50, atm, atm + 50, atm + 100}
        keep.append(g[g["strike"].isin(allowed)])
    return pd.concat(keep, ignore_index=True) if keep else df.iloc[0:0]


def find_cross(df: pd.DataFrame) -> pd.DataFrame:
    cross_rows = []
    for strike, g in df.groupby("strike"):
        g = g.sort_values("timestamp").reset_index(drop=True)
        for i in range(len(g) - 1):
            d_now, g_now = g.loc[i, "delta_spike"], g.loc[i, "gamma_spike"]
            d_next, g_next = g.loc[i+1, "delta_spike"], g.loc[i+1, "gamma_spike"]

            if d_now and not g_now and g_next and not d_next:
                cross_rows.append({
                    "strike": strike,
                    "t1": g.loc[i, "timestamp"], "t2": g.loc[i+1, "timestamp"],
                    "delta_pct_t1": round(g.loc[i, "delta_pct"], 1),
                    "gamma_pct_t2": round(g.loc[i+1, "gamma_pct"], 1),
                    "pattern": "delta_then_gamma"
                })
            if g_now and not d_now and d_next and not g_next:
                cross_rows.append({
                    "strike": strike,
                    "t1": g.loc[i, "timestamp"], "t2": g.loc[i+1, "timestamp"],
                    "gamma_pct_t1": round(g.loc[i, "gamma_pct"], 1),
                    "delta_pct_t2": round(g.loc[i+1, "delta_pct"], 1),
                    "pattern": "gamma_then_delta"
                })
    return pd.DataFrame(cross_rows)


def report_day(df: pd.DataFrame, date, side: str):
    spiked = analyze(df, side)
    spiked = filter_near_atm(spiked)

    both = spiked[spiked["delta_spike"] & spiked["gamma_spike"]]
    cross_df = find_cross(spiked)

    d_then_g = cross_df[cross_df["pattern"] == "delta_then_gamma"] if not cross_df.empty else pd.DataFrame()
    g_then_d = cross_df[cross_df["pattern"] == "gamma_then_delta"] if not cross_df.empty else pd.DataFrame()

    print(f"\n  -- {side.upper()} side --")

    print(f"  Same-bar (delta AND gamma >= {THRESH}%): {len(both)}")
    if not both.empty:
        b = both[["timestamp", "strike", "delta_pct", "gamma_pct"]].copy()
        b["delta_pct"] = b["delta_pct"].round(1)
        b["gamma_pct"] = b["gamma_pct"].round(1)
        print(b.to_string(index=False))

    print(f"  Cross: delta spike -> gamma spike (next bar): {len(d_then_g)}")
    if not d_then_g.empty:
        print(d_then_g[["strike","t1","delta_pct_t1","t2","gamma_pct_t2"]].to_string(index=False))

    print(f"  Cross: gamma spike -> delta spike (next bar): {len(g_then_d)}")
    if not g_then_d.empty:
        print(g_then_d[["strike","t1","gamma_pct_t1","t2","delta_pct_t2"]].to_string(index=False))


def _load_final_engine():
    if not STRATEGY3_DIR.exists():
        raise SystemExit(f"Strategy3MAGreeks folder not found: {STRATEGY3_DIR}")
    if str(STRATEGY3_DIR) not in sys.path:
        sys.path.insert(0, str(STRATEGY3_DIR))
    import greeks_signal_engine_final as engine
    return engine


def _filter_nearest_expiry(history: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    if "expiry" not in history.columns:
        return history, {}

    history = history.copy()
    history["expiry_dt"] = pd.to_datetime(history["expiry"], errors="coerce").dt.date
    history["trade_date"] = history["timestamp"].dt.date

    selected = {}
    keep_parts = []
    for trade_date, day in history.groupby("trade_date"):
        expiries = sorted(x for x in day["expiry_dt"].dropna().unique() if x >= trade_date)
        if not expiries:
            expiries = sorted(day["expiry_dt"].dropna().unique())
        if not expiries:
            keep_parts.append(day)
            continue
        expiry = expiries[0]
        selected[trade_date] = expiry
        keep_parts.append(day[day["expiry_dt"] == expiry])

    filtered = pd.concat(keep_parts, ignore_index=True) if keep_parts else history.iloc[0:0]
    return filtered.drop(columns=["expiry_dt", "trade_date"], errors="ignore"), selected


def run_engine_entries(selected: list[Path], args):
    engine = _load_final_engine()

    frames = []
    for db_file in selected:
        df = engine.load_oi_db(db_file)
        if not df.empty:
            frames.append(df)

    if not frames:
        raise SystemExit("No rows loaded from selected OI DB files.")

    history = pd.concat(frames, ignore_index=True)
    from_date = pd.Timestamp(args.from_date).date()
    to_date = pd.Timestamp(args.to_date).date() if args.to_date else None
    history = history[history["timestamp"].dt.date >= from_date]
    if to_date:
        history = history[history["timestamp"].dt.date <= to_date]
    expiry_map = {}
    if not args.all_expiries:
        history, expiry_map = _filter_nearest_expiry(history)
    history = engine._clean_oi(history)

    indicators = engine.load_nifty_indicators(args.nifty_excel, args.nifty_sheet)
    signals = engine.generate_signals(history, indicators, debug=args.debug)

    print("\n" + "=" * 132)
    print("  FINAL ENGINE ENTRY SIGNALS  (from spike_finder_db OI source)")
    print("=" * 132)
    print(f"  OI files      : {len(selected)}")
    print(f"  OI rows       : {len(history):,}")
    print(f"  OI range      : {history['timestamp'].min()} -> {history['timestamp'].max()}")
    if expiry_map:
        expiry_text = ", ".join(f"{d}:{e}" for d, e in sorted(expiry_map.items()))
        print(f"  Expiry mode   : nearest per date ({expiry_text})")
    else:
        print(f"  Expiry mode   : all / not available")
    print(f"  Nifty filters : {'ON' if not indicators.empty else 'OFF'}")
    print(f"  Entries       : {len(signals)}")

    if signals.empty:
        return signals

    cols = [
        "entry_time", "option", "strike", "strike_type", "expiry",
        "spot", "atm", "option_entry_price", "tier", "score",
        "oi_type", "opp_oi_type", "delta_pct", "gamma_pct",
        "iv_pct", "price_pct", "cross_confirm",
        "vwap_at_entry", "ema9_at_entry", "ema200_at_entry",
        "spot_vs_vwap", "spot_vs_200ma", "reasons",
    ]
    cols = [c for c in cols if c in signals.columns]
    view = signals[cols].copy()

    if args.export:
        out = Path(args.export)
        out.parent.mkdir(parents=True, exist_ok=True)
        view.to_csv(out, index=False)
        print(f"  Exported      : {out}")

    if args.max_print and len(view) > args.max_print:
        print(f"\nShowing first {args.max_print} of {len(view)} entries. Export has all rows.")
        print(view.head(args.max_print).to_string(index=False, max_colwidth=70))
    else:
        print("\n" + view.to_string(index=False, max_colwidth=70))
    print("\n" + "-" * 132)
    print(signals.groupby([signals["entry_time"].dt.date, "option"]).size().to_string())
    print("-" * 132)
    return signals


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--oi-db", required=True, help="Folder containing oi_*.db files, or a single .db file")
    p.add_argument("--from-date", required=True, help="YYYY-MM-DD — start reading from this date")
    p.add_argument("--to-date", default=None, help="YYYY-MM-DD — optional end date (default: latest available)")
    p.add_argument("--threshold", type=float, default=10.0, help="spike threshold %% (default 10)")
    p.add_argument("--engine-entries", action="store_true",
                   help="Run greeks_signal_engine_final.py entry algorithm and print accepted entries")
    p.add_argument("--nifty-excel", default=str(DEFAULT_NIFTY_EXCEL),
                   help="Nifty 1min Excel for VWAP/EMA filters used by final engine")
    p.add_argument("--nifty-sheet", default="1min",
                   help="Nifty Excel sheet name used by final engine")
    p.add_argument("--export", default=None,
                   help="Optional CSV export path for --engine-entries output")
    p.add_argument("--debug", action="store_true",
                   help="Print final-engine rejection counts in --engine-entries mode")
    p.add_argument("--max-print", type=int, default=200,
                   help="Max rows to print in --engine-entries mode; use 0 to print all")
    p.add_argument("--all-expiries", action="store_true",
                   help="Do not filter to nearest expiry before final-engine entry scan")
    args = p.parse_args()

    global THRESH
    THRESH = args.threshold

    db_path = Path(args.oi_db)
    if db_path.is_dir():
        dbs = sorted(db_path.glob("oi_*.db"))
    else:
        dbs = [db_path]

    from_date = pd.Timestamp(args.from_date).date()
    to_date   = pd.Timestamp(args.to_date).date() if args.to_date else None

    selected = []
    for d in dbs:
        fdate = _date_from_filename(d)
        if fdate is None:
            continue
        if fdate < from_date:
            continue
        if to_date and fdate > to_date:
            continue
        selected.append(d)

    if not selected:
        raise SystemExit(f"No oi_*.db files found from {args.from_date} onwards in {args.oi_db}")

    if args.engine_entries:
        run_engine_entries(selected, args)
        return

    for db_file in selected:
        date = _date_from_filename(db_file)
        df = load_oi_db(db_file)
        if df.empty:
            continue

        print(f"\n{'='*70}")
        print(f"  {date}  ({db_file.name})")
        print(f"{'='*70}")

        for side in ["call", "put"]:
            report_day(df, date, side)


if __name__ == "__main__":
    main()
