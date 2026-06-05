from fastapi import APIRouter
from sqlalchemy.orm import Session
import pandas as pd

from app.database import (
    SessionLocal,
    OISnapshot
)

from app.calculations import (
    get_atm_strike,
    generate_oi_table,
    generate_greek_spikes
)
from app.config import (
    get_data_date,
    STRIKE_STEP,
    TRACK_EXPIRY
)

router = APIRouter()

# =========================================
# ATM API
# =========================================

@router.get("/api/atm")

def get_atm_data(interval: str = "5m"):

    db: Session = SessionLocal()

    try:

        # =================================
        # FETCH ALL DATA (Filter by expiry)
        # =================================

        rows = db.query(OISnapshot).filter(
            OISnapshot.expiry == TRACK_EXPIRY
        ).all()

        if not rows:

            return {
                "error": "No data found"
            }

        # =================================
        # CONVERT TO DATAFRAME
        # =================================

        data = []

        for row in rows:

            data.append({

                "timestamp": row.timestamp,

                "strike": row.strike,

                "spot": row.spot,

                "call_ltp": row.call_price,
                "put_ltp": row.put_price,

                "call_oi": row.call_oi,
                "put_oi": row.put_oi,

                "call_price": row.call_price,
                "put_price": row.put_price,

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

        # =================================
        # DEBUG: Check what's in the database
        # =================================
        
        if len(df) > 0:
            print(f"\n=== ATM Route Debug ===")
            print(f"Total records: {len(df)}")
            print(f"Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
            print(f"Unique strikes: {sorted(df['strike'].unique())}")
            print(f"Sample OI values for ATM at latest time:")
            latest_time = df['timestamp'].max()
            latest_data = df[df['timestamp'] == latest_time]
            for _, row in latest_data.head(5).iterrows():
                print(f"  Strike: {row['strike']}, Call_OI: {row['call_oi']}, Put_OI: {row['put_oi']}")
            print("===\n")

        # =================================
        # SORT BY TIMESTAMP
        # =================================

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")

        # =================================
        # LATEST SPOT
        # =================================

        latest = df.iloc[-1]

        spot = latest["spot"]

        atm = get_atm_strike(spot)

        # =================================
        # GENERATE CE TABLE
        # =================================

        ce_data = generate_oi_table(
            history_df=df,
            strike=atm,
            option_type="CE",
            interval_name=interval
        )

        # =================================
        # GENERATE PE TABLE
        # =================================

        pe_data = generate_oi_table(
            history_df=df,
            strike=atm,
            option_type="PE",
            interval_name=interval
        )

        # =================================
        # LAST UPDATE
        # =================================

        latest_timestamp = str(latest["timestamp"])
        earliest_timestamp = str(df.iloc[0]["timestamp"])


        # =================================
        # RESPONSE
        # =================================

        return {

            "spot": spot,

            "atm": atm,

            "interval": interval,

            "last_update": latest_timestamp,
            "earliest_update": earliest_timestamp,
            "data_date": get_data_date(),

            "ce_data": ce_data,

            "pe_data": pe_data

        }

    finally:
        db.close()


@router.get("/api/greeks")

def get_greeks_data(
    interval: str = "5m",
    strike: int = None
):

    db: Session = SessionLocal()

    try:

        rows = db.query(OISnapshot).all()

        if not rows:

            return {
                "error": "No data found"
            }

        data = []

        for row in rows:

            data.append({

                "timestamp": row.timestamp,

                "strike": row.strike,

                "spot": row.spot,

                "call_oi": row.call_oi,
                "put_oi": row.put_oi,

                "call_price": row.call_price,
                "put_price": row.put_price,

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

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")

        opening = df.iloc[0]
        latest = df.iloc[-1]

        spot = latest["spot"]
        opening_spot = opening["spot"]
        opening_atm = get_atm_strike(opening_spot)

        strike_options = [
            opening_atm + i
            for i in range(-500, 501, STRIKE_STEP)
        ]

        if strike is None or strike not in strike_options:
            strike = opening_atm
        ce_spikes = generate_greek_spikes(
            history_df=df,
            strike=strike,
            option_type="CE",
            interval_name=interval
        )

        pe_spikes = generate_greek_spikes(
            history_df=df,
            strike=strike,
            option_type="PE",
            interval_name=interval
        )

        latest_timestamp = str(latest["timestamp"])
        earliest_timestamp = str(opening["timestamp"])

        return {
            "spot": spot,
            "opening_atm": opening_atm,
            "strike": strike,
            "strike_options": strike_options,
            "interval": interval,
            "last_update": latest_timestamp,
            "earliest_update": earliest_timestamp,
            "data_date": get_data_date(),
            "ce_spikes": ce_spikes,
            "pe_spikes": pe_spikes
        }

    finally:
        db.close()
