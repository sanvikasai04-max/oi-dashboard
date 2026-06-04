import argparse
import sqlite3
import pandas as pd


def percent_change(current, previous):
    if previous == 0:
        return 0
    return ((current - previous) / abs(previous)) * 100


parser = argparse.ArgumentParser()
parser.add_argument("db")
parser.add_argument("--strike", type=float, required=True)
parser.add_argument("--delta-threshold", type=float, default=10)
parser.add_argument("--gamma-threshold", type=float, default=10)

args = parser.parse_args()

conn = sqlite3.connect(args.db)

df = pd.read_sql_query(
    """
    SELECT *
    FROM oi_snapshots
    WHERE strike = ?
    ORDER BY timestamp
    """,
    conn,
    params=[args.strike],
)

conn.close()

df["timestamp"] = pd.to_datetime(df["timestamp"])
df["interval"] = df["timestamp"].dt.floor("5min")

idx = df.groupby("interval")["timestamp"].idxmax()

df = (
    df.loc[idx]
    .sort_values("interval")
    .reset_index(drop=True)
)

print("\n")
print("=" * 100)
print(f"DELTA + GAMMA SPIKES : STRIKE {int(args.strike)}")
print("=" * 100)

for i in range(1, len(df)):

    curr = df.iloc[i]
    prev = df.iloc[i - 1]

    time_label = curr["interval"].strftime("%H:%M")

    # ---------------- CE ----------------

    ce_delta_pct = percent_change(
        abs(curr["call_delta"]),
        abs(prev["call_delta"])
    )

    ce_gamma_pct = percent_change(
        curr["call_gamma"],
        prev["call_gamma"]
    )

    if (
        curr["call_delta"] > prev["call_delta"]
        and curr["call_gamma"] > prev["call_gamma"]
        and ce_delta_pct >= args.delta_threshold
        and ce_gamma_pct >= args.gamma_threshold
    ):

        print(
            f"{time_label} | CE | "
            f"LTP={curr['call_price']:.2f} | "
            f"Delta={curr['call_delta']:.4f} "
            f"({ce_delta_pct:.2f}%) | "
            f"Gamma={curr['call_gamma']:.6f} "
            f"({ce_gamma_pct:.2f}%)"
        )

    # ---------------- PE ----------------

    pe_delta_pct = percent_change(
        abs(curr["put_delta"]),
        abs(prev["put_delta"])
    )

    pe_gamma_pct = percent_change(
        curr["put_gamma"],
        prev["put_gamma"]
    )

    if (
        abs(curr["put_delta"]) > abs(prev["put_delta"])
        and curr["put_gamma"] > prev["put_gamma"]
        and pe_delta_pct >= args.delta_threshold
        and pe_gamma_pct >= args.gamma_threshold
    ):

        print(
            f"{time_label} | PE | "
            f"LTP={curr['put_price']:.2f} | "
            f"Delta={curr['put_delta']:.4f} "
            f"({pe_delta_pct:.2f}%) | "
            f"Gamma={curr['put_gamma']:.6f} "
            f"({pe_gamma_pct:.2f}%)"
        )