import argparse
import sqlite3
import pandas as pd
from pathlib import Path

# ---------- Arguments ----------
parser = argparse.ArgumentParser(
    description="Convert SQLite DB to Excel"
)

parser.add_argument(
    "db_file",
    help="SQLite database file"
)

args = parser.parse_args()

db_file = args.db_file

# ---------- Output Excel ----------
excel_file = Path(db_file).with_suffix(".xlsx")

# ---------- Connect ----------
conn = sqlite3.connect(db_file)

tables = pd.read_sql(
    "SELECT name FROM sqlite_master WHERE type='table'",
    conn
)

with pd.ExcelWriter(excel_file, engine="openpyxl") as writer:

    for table in tables["name"]:
        print(f"Exporting table: {table}")

        df = pd.read_sql(
            f"SELECT * FROM {table}",
            conn
        )

        df.to_excel(
            writer,
            sheet_name=table[:31],
            index=False
        )

conn.close()

print(f"\n✅ Exported: {excel_file}")