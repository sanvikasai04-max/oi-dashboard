"""
Script 1: Convert oi_snapshots SQLite DB → CSV
Usage: python 1_db_to_csv.py
Output: oi_2026_06_15.csv (same folder as the .db file)
"""

import sqlite3
import pandas as pd
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
DB_PATH  = "oi_2026_06_16.db"          # change path if needed
CSV_PATH = "oi_2026_06_16.csv"         # output CSV
TABLE    = "oi_snapshots"
# ─────────────────────────────────────────────────────────────────────────────

def main():
    db = Path(DB_PATH)
    if not db.exists():
        raise FileNotFoundError(f"DB not found: {DB_PATH}")

    print(f"Reading '{TABLE}' from {DB_PATH} …")
    conn = sqlite3.connect(DB_PATH)
    df   = pd.read_sql(f"SELECT * FROM {TABLE} ORDER BY timestamp, strike", conn)
    conn.close()

    # Clean up: parse timestamp properly
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    df.to_csv(CSV_PATH, index=False)
    print(f"✅  Saved {len(df):,} rows → {CSV_PATH}")
    print(f"    Columns : {list(df.columns)}")
    print(f"    Date range: {df['timestamp'].min()}  →  {df['timestamp'].max()}")
    print(f"    Strikes : {df['strike'].nunique()} unique  ({df['strike'].min()} – {df['strike'].max()})")


if __name__ == "__main__":
    main()
