from fastapi import APIRouter
from sqlalchemy.orm import Session
import pandas as pd

from app.database import (
    SessionLocal,
    OISnapshot
)
from app.config import TRACK_EXPIRY, get_data_iso_date

router = APIRouter()

# =========================================
# HISTORICAL API
# =========================================

@router.get("/api/historical")

def get_historical_data(limit: int = 500):

    db: Session = SessionLocal()

    try:

        # =================================
        # FETCH LIMITED DATA
        # =================================

        query = db.query(OISnapshot).filter(
            OISnapshot.expiry == TRACK_EXPIRY
        )

        data_iso_date = get_data_iso_date()

        if data_iso_date:
            query = query.filter(
                OISnapshot.timestamp.like(f"{data_iso_date}%")
            )

        rows = (
            query
            .order_by(OISnapshot.id.desc())
            .limit(limit)
            .all()
        )

        if not rows:

            return {
                "error": "No historical data found"
            }

        # =================================
        # CONVERT TO JSON
        # =================================

        historical_data = []

        for row in rows:

            historical_data.append({

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

        # =================================
        # RESPONSE
        # =================================

        return {

            "count": len(historical_data),

            "data": historical_data

        }

    finally:

        db.close()
