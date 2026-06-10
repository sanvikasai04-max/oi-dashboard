import datetime as dt
import os
import re
# =========================================
# DHAN CONFIG
# =========================================

CLIENT_ID = "1107485546"
ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzUxMiJ9.eyJpc3MiOiJkaGFuIiwicGFydG5lcklkIjoiIiwiZXhwIjoxNzgxMTQ5NjU2LCJpYXQiOjE3ODEwNjMyNTYsInRva2VuQ29uc3VtZXJUeXBlIjoiU0VMRiIsIndlYmhvb2tVcmwiOiIiLCJkaGFuQ2xpZW50SWQiOiIxMTA3NDg1NTQ2In0.QrL8HtwG-EJAMIySAtuoYXB8j9bupWY90hDus5YKrEVl_QS31Z-sDC5RI7KfZFTljbkSvYUV1In34xnCVVGDQg"
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

DATABASE_URL = f"sqlite:///./oi_{today}.db"

#DATABASE_URL = "sqlite:///./oi_2026_06_02.db"


def get_database_date():
    match = re.search(r"(\d{4})[_-](\d{2})[_-](\d{2})\.db", DATABASE_URL)

    if not match:
        return None

    year, month, day = match.groups()
    return dt.date(int(year), int(month), int(day))


def get_data_iso_date():
    data_date = get_database_date()

    if data_date is None:
        return None

    return data_date.isoformat()


def get_data_date():
    data_date = get_database_date()

    if data_date is None:
        return None

    return data_date.strftime("%d %b %Y")

# =========================================
# MARKET SETTINGS
# =========================================

UNDERLYING_SCRIP = 13

UNDERLYING_SEGMENT = "IDX_I"

# =========================================
# EXPIRY SETTINGS (Which expiry to track)
# =========================================

TRACK_EXPIRY = "2026-06-16"  # Current week Thursday (June 16)

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
