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
# DASHBOARD API
# =========================================

@router.get("/api/dashboard")

def get_dashboard_data(interval: str = "5m"):

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

        # =================================
        # SORT BY TIMESTAMP
        # =================================

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")

        latest = df.iloc[-1]

        spot = latest["spot"]

        atm = get_atm_strike(spot)

        otm = atm + 50

        # =================================
        # ATM
        # =================================

        atm_ce_data = generate_oi_table(
            history_df=df,
            strike=atm,
            option_type="CE",
            interval_name=interval
        )

        atm_pe_data = generate_oi_table(
            history_df=df,
            strike=atm,
            option_type="PE",
            interval_name=interval
        )

        # =================================
        # OTM
        # =================================

        otm_ce_data = generate_oi_table(
            history_df=df,
            strike=otm,
            option_type="CE",
            interval_name=interval
        )

        otm_pe_data = generate_oi_table(
            history_df=df,
            strike=otm,
            option_type="PE",
            interval_name=interval
        )

        last_update = str(latest["timestamp"])
        earliest_update = str(df.iloc[0]["timestamp"])

        return {

            "spot": spot,

            "atm": atm,
            "otm": otm,
            "last_update": last_update,
            "earliest_update": earliest_update,
            "data_date": get_data_date(),

            "atm_ce_data": atm_ce_data,
            "atm_pe_data": atm_pe_data,

            "otm_ce_data": otm_ce_data,
            "otm_pe_data": otm_pe_data

        }

    finally:

        db.close()

# =========================================
# ITM API
# =========================================

@router.get("/api/itm")

def get_itm_data(interval: str = "5m"):

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

        # =================================
        # SORT BY TIMESTAMP
        # =================================

        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values("timestamp")

        latest = df.iloc[-1]

        spot = latest["spot"]

        atm = get_atm_strike(spot)

        itm50 = atm - 50
        itm100 = atm - 100

        # =================================
        # ITM -50
        # =================================

        itm50_ce_data = generate_oi_table(
            history_df=df,
            strike=itm50,
            option_type="CE",
            interval_name=interval
        )

        itm50_pe_data = generate_oi_table(
            history_df=df,
            strike=itm50,
            option_type="PE",
            interval_name=interval
        )

        # =================================
        # ITM -100
        # =================================

        itm100_ce_data = generate_oi_table(
            history_df=df,
            strike=itm100,
            option_type="CE",
            interval_name=interval
        )

        itm100_pe_data = generate_oi_table(
            history_df=df,
            strike=itm100,
            option_type="PE",
            interval_name=interval
        )

        last_update = str(latest["timestamp"])
        earliest_update = str(df.iloc[0]["timestamp"])

        return {

            "spot": spot,

            "itm50": itm50,
            "itm100": itm100,
            "last_update": last_update,
            "earliest_update": earliest_update,
            "data_date": get_data_date(),

            "itm50_ce_data": itm50_ce_data,
            "itm50_pe_data": itm50_pe_data,

            "itm100_ce_data": itm100_ce_data,
            "itm100_pe_data": itm100_pe_data

        }

    finally:

        db.close()
