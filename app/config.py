import datetime as dt
import os
import re
# =========================================
# DHAN CONFIG
# =========================================

CLIENT_ID = os.getenv("DHAN_CLIENT_ID", "")
ACCESS_TOKEN = os.getenv("DHAN_ACCESS_TOKEN", "")
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

DATABASE_URL = "sqlite:///./oi_2026_05_26.db"


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
