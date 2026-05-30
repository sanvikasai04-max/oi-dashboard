from fastapi import APIRouter
from sqlalchemy.orm import Session
import pandas as pd

from app.database import (
    SessionLocal,
    OISnapshot
)

from app.calculations import (
    get_atm_strike,
    generate_oi_table
)
from app.config import get_data_date

router = APIRouter()

# =========================================
# ATM API
# =========================================

@router.get("/api/atm")

def get_atm_data(interval: str = "5m"):

    db: Session = SessionLocal()

    try:

        # =================================
        # FETCH ALL DATA
        # =================================

        rows = db.query(OISnapshot).all()

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
