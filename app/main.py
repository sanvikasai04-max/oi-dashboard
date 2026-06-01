from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

import threading
import time

from app.database import create_tables
from app.collector import collect_and_store

# =========================================
# IMPORT ROUTERS
# =========================================

from app.routes.atm import router as atm_router
from app.routes.itm_otm import router as itm_otm_router
from app.routes.historical import router as historical_router

# =========================================
# FASTAPI APP
# =========================================

app = FastAPI()

# =========================================
# INCLUDE ROUTERS
# =========================================

app.include_router(atm_router)
app.include_router(itm_otm_router)
app.include_router(historical_router)

# =========================================
# STATIC FILES
# =========================================

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static"
)

# =========================================
# TEMPLATES
# =========================================

templates = Jinja2Templates(
    directory="app/templates"
)

# =========================================
# CREATE DATABASE TABLES
# =========================================

create_tables()

# =========================================
# BACKGROUND COLLECTOR LOOP
# =========================================

def background_collector():

    while True:

        print("Collecting market data...")

        try:

            snapshot_saved = collect_and_store()

            if snapshot_saved:

                print("Snapshot saved successfully")

        except Exception as e:

            print("COLLECTOR ERROR:", e)

        # 1 minute for Greeks
        time.sleep(60)


#Comment out  for backtest
# =========================================
# START COLLECTOR ON STARTUP
# =========================================

@app.on_event("startup")
def start_collector():

    collector_thread = threading.Thread(
        target=background_collector,
        daemon=True
    )

    collector_thread.start()

# =========================================
# HOME
# =========================================

@app.get("/")
def home():

    return {
        "message": "OI Dashboard Running"
    }

# =========================================
# ATM PAGE
# =========================================
# =========================================
# DASHBOARD PAGE
# =========================================

@app.get("/dashboard")
def dashboard_page(request: Request):

    return templates.TemplateResponse(
    request,
    "dashboard.html"
)

# =========================================
# ITM PAGE
# =========================================
@app.get("/itm")
def itm_page(request: Request):

    return templates.TemplateResponse(
        request,
        "itm.html"
    )

# =========================================
# ATM GREEKS CHARTS PAGE
# =========================================

@app.get("/greeks")
def greeks_page(request: Request):

    return templates.TemplateResponse(
        request,
        "greeks.html"
    )
