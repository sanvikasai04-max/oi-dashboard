"""
dhan_rolling_nifty_greeks_fetch.py
Fetch PAST / EXPIRED NIFTY option data from Dhan Rolling Options API,
calculate Delta/Gamma from Dhan IV, and save to SQLite oi_snapshots table.

IMPORTANT:
- This uses /v2/charts/rollingoption, NOT intraday_minute_data.
- It does not need expired security_id / old instrument master.
- Dhan returns rolling strike like ATM, ATM+1, ATM-1 ... up to ATM±10 for index options.
- For last week expiry, pass expiry-code 1 with expiry-flag WEEK. If you need previous weekly
  expiries, try expiry-code 2, 3, 4 etc.

Install:
  pip install pandas numpy scipy requests openpyxl

Example:
  set DHAN_CLIENT_ID=1107485546
  set DHAN_ACCESS_TOKEN=YOUR_TOKEN

  python dhan_rolling_nifty_greeks_fetch.py ^
    --nifty-excel "nifty_live_all_timeframes.xlsx" ^
    --from-date 2026-06-05 ^
    --to-date 2026-06-10 ^
    --expiry-date 2026-06-09 ^
    --expiry-flag WEEK ^
    --expiry-code 1 ^
    --interval 1 ^
    --atm-range 5
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests
from scipy.stats import norm

API_URL = "https://api.dhan.co/v2/charts/rollingoption"
NIFTY_UNDERLYING_SECURITY_ID = 13


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--client-id", default=os.getenv("DHAN_CLIENT_ID"), help="Dhan client id or env DHAN_CLIENT_ID")
    p.add_argument("--access-token", default=os.getenv("DHAN_ACCESS_TOKEN"), help="Dhan access token or env DHAN_ACCESS_TOKEN")
    p.add_argument("--nifty-excel", default="nifty_live_all_timeframes.xlsx")
    p.add_argument("--sheet", default="1min")
    p.add_argument("--from-date", required=True, help="YYYY-MM-DD. Include expiry week start/trading date")
    p.add_argument("--to-date", required=True, help="YYYY-MM-DD. Dhan says toDate is non-inclusive, so use expiry date + 1")
    p.add_argument("--expiry-date", required=True, help="YYYY-MM-DD actual expiry date for time-to-expiry calculation")
    p.add_argument("--expiry-flag", default="WEEK", choices=["WEEK", "MONTH"])
    p.add_argument("--expiry-code", type=int, default=1, help="1=nearest/last matching rolling expiry. Try 2/3/4 for older weekly expiries")
    p.add_argument("--interval", default="1", choices=["1", "5", "15", "25", "60"])
    p.add_argument("--atm-range", type=int, default=5, help="Fetch ATM±N. Dhan supports up to 10 for index options")
    p.add_argument("--risk-free", type=float, default=0.065)
    p.add_argument("--db-file", default=None)
    p.add_argument("--sleep", type=float, default=0.4)
    return p.parse_args()


def load_spot_excel(path: str, sheet: str) -> dict[str, float]:
    df = pd.read_excel(path, sheet_name=sheet)
    cols = {c.lower().strip(): c for c in df.columns}
    if "datetime" not in cols or "close" not in cols:
        raise SystemExit(f"Excel must have datetime and close columns. Found: {list(df.columns)}")
    dt_col, close_col = cols["datetime"], cols["close"]
    ts = pd.to_datetime(df[dt_col], format="%d-%m-%Y %H:%M", errors="coerce")
    if ts.isna().all():
        ts = pd.to_datetime(df[dt_col], errors="coerce", dayfirst=True)
    out = df.assign(_ts=ts).dropna(subset=["_ts", close_col]).sort_values("_ts")
    return {r["_ts"].strftime("%Y-%m-%d %H:%M"): float(r[close_col]) for _, r in out.iterrows()}


def strike_labels(atm_range: int) -> list[str]:
    n = max(0, min(10, atm_range))
    labels = ["ATM"]
    for i in range(1, n + 1):
        labels.append(f"ATM-{i}")
        labels.append(f"ATM+{i}")
    return labels


def call_dhan(args: argparse.Namespace, strike_label: str, opt: str) -> dict[str, Any] | None:
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "access-token": args.access_token,
        "client-id": args.client_id,
    }
    payload = {
        "exchangeSegment": "NSE_FNO",
        "interval": str(args.interval),
        "securityId": NIFTY_UNDERLYING_SECURITY_ID,
        "instrument": "OPTIDX",
        "expiryFlag": args.expiry_flag,
        "expiryCode": args.expiry_code,
        "strike": strike_label,
        "drvOptionType": opt,
        "requiredData": ["open", "high", "low", "close", "iv", "volume", "strike", "oi", "spot"],
        "fromDate": args.from_date,
        "toDate": args.to_date,
    }
    for attempt in range(1, 6):
        try:
            r = requests.post(API_URL, headers=headers, json=payload, timeout=30)
            if r.status_code in (429, 500, 502, 503, 504):
                wait = attempt * 5
                print(f"      rate/server issue {r.status_code}; wait {wait}s")
                time.sleep(wait)
                continue
            data = r.json()
            if r.status_code != 200 or data.get("status") == "failure":
                print(f"      Dhan error {r.status_code}: {data}")
                return None
            return data.get("data") or data
        except Exception as e:
            print(f"      request failed: {e}")
            time.sleep(attempt * 3)
    return None


def normalize_leg(resp_data: dict[str, Any], opt: str) -> pd.DataFrame:
    key = "ce" if opt == "CALL" else "pe"
    leg = resp_data.get(key) if isinstance(resp_data, dict) else None
    if not leg:
        return pd.DataFrame()
    ts = leg.get("timestamp") or []
    if not ts:
        return pd.DataFrame()
    dt = pd.to_datetime(ts, unit="s", utc=True).tz_convert("Asia/Kolkata").tz_localize(None)
    n = len(ts)
    def arr(name, default=np.nan):
        x = leg.get(name)
        if x is None:
            return [default] * n
        if len(x) < n:
            return list(x) + [default] * (n - len(x))
        return list(x[:n])
    return pd.DataFrame({
        "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
        "ts_min": dt.strftime("%Y-%m-%d %H:%M"),
        "close": arr("close"),
        "volume": arr("volume", 0),
        "oi": arr("oi", 0),
        "iv": arr("iv"),
        "strike": arr("strike"),
        "spot_dhan": arr("spot"),
    })


def greeks_from_iv(S: float, K: float, T: float, r: float, iv_value: float, opt: str):
    if pd.isna(S) or pd.isna(K) or pd.isna(iv_value) or S <= 0 or K <= 0 or T <= 0:
        return None, None
    sigma = float(iv_value)
    if sigma > 3:  # Dhan IV usually comes as percent, e.g. 18.5
        sigma = sigma / 100.0
    if sigma <= 0:
        return None, None
    d1 = (np.log(S / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * np.sqrt(T))
    delta = norm.cdf(d1) if opt == "CE" else norm.cdf(d1) - 1
    gamma = norm.pdf(d1) / (S * sigma * np.sqrt(T))
    return round(float(delta), 6), round(float(gamma), 8)


def init_db(db_file: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_file)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS oi_snapshots (
            id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
            timestamp VARCHAR,
            strike FLOAT,
            spot FLOAT,
            call_oi INTEGER,
            put_oi INTEGER,
            call_price FLOAT,
            put_price FLOAT,
            call_volume INTEGER,
            put_volume INTEGER,
            call_delta FLOAT,
            put_delta FLOAT,
            call_gamma FLOAT,
            put_gamma FLOAT,
            call_iv FLOAT,
            put_iv FLOAT,
            expiry TEXT
        )
    """)
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ts_expiry_strike
        ON oi_snapshots (timestamp, expiry, strike)
    """)
    conn.commit()
    return conn


def main() -> None:
    args = parse_args()
    if not args.client_id or not args.access_token:
        raise SystemExit("Set --client-id/--access-token or env DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN")
    if not Path(args.nifty_excel).exists():
        raise SystemExit(f"NIFTY Excel not found: {args.nifty_excel}")
    db_file = args.db_file or f"oi_{args.expiry_date.replace('-', '_')}.db"

    spot_lookup = load_spot_excel(args.nifty_excel, args.sheet)
    expiry_dt = datetime.strptime(args.expiry_date + " 15:30:00", "%Y-%m-%d %H:%M:%S")
    conn = init_db(db_file)

    total = 0
    for label in strike_labels(args.atm_range):
        print(f"\nFetching {label} CALL/PUT ...")
        ce_resp = call_dhan(args, label, "CALL")
        time.sleep(args.sleep)
        pe_resp = call_dhan(args, label, "PUT")
        time.sleep(args.sleep)
        if not ce_resp or not pe_resp:
            print("   skipped: empty response")
            continue
        ce = normalize_leg(ce_resp, "CALL")
        pe = normalize_leg(pe_resp, "PUT")
        if ce.empty or pe.empty:
            print(f"   skipped: CE bars={len(ce)} PE bars={len(pe)}")
            continue

        m = ce.add_prefix("ce_").merge(
            pe.add_prefix("pe_"),
            left_on=["ce_timestamp", "ce_ts_min"],
            right_on=["pe_timestamp", "pe_ts_min"],
            how="inner",
        )
        rows = []
        for _, row in m.iterrows():
            ts = row["ce_timestamp"]
            ts_min = row["ce_ts_min"]
            bar_dt = datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
            T = max((expiry_dt - bar_dt).total_seconds() / (365.25 * 24 * 3600), 1e-9)

            # Use Dhan spot first; fallback to uploaded NIFTY Excel close.
            spot = row.get("ce_spot_dhan")
            if pd.isna(spot) or float(spot) <= 0:
                spot = spot_lookup.get(ts_min)
            if spot is None:
                continue
            spot = float(spot)

            # Dhan rolling API returns the actual strike in each row.
            ce_k = row.get("ce_strike")
            pe_k = row.get("pe_strike")
            K = ce_k if not pd.isna(ce_k) else pe_k
            if pd.isna(K):
                continue
            K = float(K)

            ce_delta, ce_gamma = greeks_from_iv(spot, K, T, args.risk_free, row.get("ce_iv"), "CE")
            pe_delta, pe_gamma = greeks_from_iv(spot, K, T, args.risk_free, row.get("pe_iv"), "PE")

            rows.append((
                ts, K, spot,
                int(0 if pd.isna(row.get("ce_oi")) else row.get("ce_oi")),
                int(0 if pd.isna(row.get("pe_oi")) else row.get("pe_oi")),
                float(row.get("ce_close")), float(row.get("pe_close")),
                int(0 if pd.isna(row.get("ce_volume")) else row.get("ce_volume")),
                int(0 if pd.isna(row.get("pe_volume")) else row.get("pe_volume")),
                ce_delta, pe_delta, ce_gamma, pe_gamma,
                None if pd.isna(row.get("ce_iv")) else float(row.get("ce_iv")),
                None if pd.isna(row.get("pe_iv")) else float(row.get("pe_iv")),
                args.expiry_date,
            ))

        if rows:
            conn.executemany("""
                INSERT OR IGNORE INTO oi_snapshots
                (timestamp, strike, spot, call_oi, put_oi, call_price, put_price,
                 call_volume, put_volume, call_delta, put_delta, call_gamma, put_gamma,
                 call_iv, put_iv, expiry)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, rows)
            conn.commit()
        total += len(rows)
        print(f"   saved rows: {len(rows)}")

    row_count = conn.execute("SELECT COUNT(*) FROM oi_snapshots").fetchone()[0]
    rng = conn.execute("SELECT MIN(timestamp), MAX(timestamp), COUNT(DISTINCT strike) FROM oi_snapshots").fetchone()
    conn.close()
    print(f"\nDONE: {db_file}")
    print(f"Rows={row_count:,} | Range={rng[0]} -> {rng[1]} | Distinct strikes={rng[2]}")


if __name__ == "__main__":
    main()
