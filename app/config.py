import datetime as dt
import os
import re
# =========================================
# DHAN CONFIG
# =========================================

CLIENT_ID = "1107485546"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzgwNTQ0NDEyLCJpYXQiOjE3ODA0NTgwMTIsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA3NDg1NTQ2In0.cqNTMh01SuYam4S3zyIL_3tAsd01S15OYMeRMKNiC_8NoRZR0_1plQ1Mlfu7sqpJdK9zEtUqXBbk3qhW-YFBfA"
# =========================================
# APP SETTINGS
# =========================================

REFRESH_INTERVAL = 300  # seconds

STRIKE_STEP = 50

ATM_STRIKE_COUNT = 2

ITM_OTM_DISTANCE = 1

# =========================================
# DATABASE
# =========================================

##############
#back test Temporarily change:

#DATABASE_URL = "sqlite:///./oi_2026_05_23.db"
#######################

today = dt.datetime.now().strftime("%Y_%m_%d")

#DATABASE_URL = f"sqlite:///./oi_{today}.db"

DATABASE_URL = "sqlite:///./oi_2026_06_03.db"


def get_data_date():
    match = re.search(r"(\d{4})[_-](\d{2})[_-](\d{2})\.db", DATABASE_URL)

    if not match:
        return None

    year, month, day = match.groups()
    return dt.date(int(year), int(month), int(day)).strftime("%d %b %Y")

# =========================================
# MARKET SETTINGS
# =========================================

UNDERLYING_SCRIP = 13

UNDERLYING_SEGMENT = "IDX_I"

# =========================================
# EXPIRY SETTINGS (Which expiry to track)
# =========================================

TRACK_EXPIRY = "2026-06-09"  # Current week Thursday (June 9)

# =========================================
# DEFAULT TIMEFRAME
# =========================================

DEFAULT_TIMEFRAME = "5m"

# =========================================
# TIMEFRAME MAP
# =========================================

INTERVAL_MAP = {
    "5m": 1,
    "15m": 3,
    "30m": 6,
    "1hr": 12
}
