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
from pathlib import Path

import pandas as pd

THRESH = 10.0  # % change threshold


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


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--oi-db", required=True, help="Folder containing oi_*.db files, or a single .db file")
    p.add_argument("--from-date", required=True, help="YYYY-MM-DD — start reading from this date")
    p.add_argument("--to-date", default=None, help="YYYY-MM-DD — optional end date (default: latest available)")
    p.add_argument("--threshold", type=float, default=10.0, help="spike threshold %% (default 10)")
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
