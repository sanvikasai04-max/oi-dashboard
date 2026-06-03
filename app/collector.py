import requests
import json
import datetime as dt
import time

try:
    from zoneinfo import ZoneInfo
except ImportError:
    ZoneInfo = None

from app.config import (
    CLIENT_ID,
    ACCESS_TOKEN,
    UNDERLYING_SCRIP,
    UNDERLYING_SEGMENT
)

from app.database import save_snapshot

# =========================================
# MARKET HOURS
# =========================================

MARKET_CLOSE_TIME = dt.time(15, 30)

if ZoneInfo is not None:
    IST_TIMEZONE = ZoneInfo("Asia/Kolkata")
else:
    IST_TIMEZONE = dt.timezone(
        dt.timedelta(hours=5, minutes=30)
    )


def get_ist_now():

    return dt.datetime.now(IST_TIMEZONE)


def is_after_market_close(now=None):

    if now is None:
        now = get_ist_now()

    return now.time() >= MARKET_CLOSE_TIME

# =========================================
# GET EXPIRY
# =========================================

def get_expiry():

    today = dt.datetime.today()

    days_ahead = (1 - today.weekday() + 7) % 7

    expiry = (
        today + dt.timedelta(days=days_ahead)
    ).strftime("%Y-%m-%d")

    print("Using expiry:", expiry)

    return expiry
# =========================================
# FETCH OPTION CHAIN
# =========================================
def get_next_n_expiries(n=5):

    today = dt.datetime.today()

    expiries = []

    days_ahead = (1 - today.weekday() + 7) % 7

    next_thursday = today + dt.timedelta(days=days_ahead)

    for i in range(n):

        expiry = (
            next_thursday + dt.timedelta(weeks=i)
        ).strftime("%Y-%m-%d")

        expiries.append(expiry)

    return expiries

def fetch_option_chain():

    headers = {
        "Content-Type": "application/json",
        "access-token": ACCESS_TOKEN,
        "client-id": CLIENT_ID
    }

    option_chain = None
    spot = None
    used_expiry = None

    expiries = get_next_n_expiries(2)

    for expiry in expiries:
        time.sleep(1)
        payload = {
            "UnderlyingScrip": UNDERLYING_SCRIP,
            "UnderlyingSeg": UNDERLYING_SEGMENT,
            "Expiry": expiry
        }

        print("Trying expiry:", expiry)

        try:

            response = requests.post(
                "https://api.dhan.co/v2/optionchain",
                headers=headers,
                data=json.dumps(payload)
            )

            print("STATUS:", response.status_code)
            try:
                print(response.json())
            except:
                print(response.text)

            if response.status_code != 200:
                continue

            data = response.json()

            if data.get("data", {}).get("oc"):

                option_chain = data["data"]["oc"]
                spot = data["data"]["last_price"]
                used_expiry = expiry

                print("Using expiry:", expiry)

                return option_chain, spot, used_expiry

        except Exception as e:

            print("FETCH ERROR:", e)

    return None, None, None
# =========================================
# SAVE MARKET SNAPSHOT
# =========================================

def collect_and_store():

    now = get_ist_now()

    if is_after_market_close(now):

        print(
            "Market closed after 15:30 IST. "
            "Skipping new snapshot save."
        )

        return False

    option_chain, spot, expiry = fetch_option_chain()

    if option_chain is None:
        return False

    timestamp = now.strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    for strike_str, values in option_chain.items():

        strike = float(strike_str)

        ce = values.get("ce", {})
        pe = values.get("pe", {})

        snapshot = {

            # =================================
            # BASIC
            # =================================

            "timestamp": timestamp,

            "expiry": expiry,

            "strike": strike,

            "spot": spot,

            # =================================
            # OI
            # =================================

            "call_oi": ce.get("oi", 0),

            "put_oi": pe.get("oi", 0),

            # =================================
            # PRICE
            # =================================

            "call_price": ce.get("last_price", 0),

            "put_price": pe.get("last_price", 0),

            # =================================
            # VOLUME
            # =================================

            "call_volume": ce.get("volume", 0),

            "put_volume": pe.get("volume", 0),

            # =================================
            # GREEKS
            # =================================

            "call_delta": ce.get("greeks", {}).get("delta", 0),

            "put_delta": pe.get("greeks", {}).get("delta", 0),

            "call_gamma": ce.get("greeks", {}).get("gamma", 0),

            "put_gamma": pe.get("greeks", {}).get("gamma", 0),

            "call_iv": ce.get("implied_volatility", 0),

            "put_iv": pe.get("implied_volatility", 0)

        }

        save_snapshot(snapshot)

    print(f"Saved snapshot at {timestamp} for expiry {expiry}")

    return True
