from fastapi import APIRouter
from sqlalchemy.orm import Session
import pandas as pd

from app.database import (
    SessionLocal,
    OISnapshot
)

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

        rows = (
            db.query(OISnapshot)
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