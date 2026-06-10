# Nifty_Live_OI_GreeksData

![OI Dashboard Preview](docs/assets/dashboard-preview.png)

```bash
pip install -r requirements.txt
```

# 📊 Institutional OI Dashboard

Professional HTML-based Option Chain OI Monitoring System using:

- FastAPI
- SQLite
- HTML/CSS/JS
- Dhan API

Supports:
- ATM Monitoring
- ITM / OTM Monitoring
- Dashboard 4 Candle Entries
- OI Build-up Analysis
- Delta / Gamma / IV
- Multi-Timeframe Analysis
- Historical Storage
- Live Dashboard Updates

---

# 🚀 Features

## ATM Dashboard
- CE / PE monitoring
- Long buildup
- Short buildup
- Short covering
- Long unwinding
- Delta
- Gamma
- IV
- Live refresh

---

## ITM / OTM Dashboard
- Smart money flow
- Hedge activity
- Trap analysis
- Liquidity analysis
- Institutional positioning

---

## Dashboard 4 - Candle Entries
- Candle view with entry markers
- Directional entries using OI + Delta + Gamma
- Bullish market: CE ATM / ITM entries
- Bearish market: PE OTM entries
- Stop loss, Target 1, Target 2
- Exit time and P&L tracking

---

## Multi-Timeframe
Supports:
- 5m
- 15m
- 30m
- 1hr

IMPORTANT:

Only 5-minute raw data is stored.

Higher timeframes are dynamically calculated.

---

# 🏗️ Project Structure

```text
oi-dashboard/

├── app/
│   ├── main.py
│   ├── collector.py
│   ├── calculations.py
│   ├── database.py
│   ├── config.py
│   │
│   ├── routes/
│   │   ├── atm.py
│   │   ├── itm_otm.py
│   │   └── historical.py
│   │
│   ├── templates/
│   │   ├── base.html
│   │   ├── atm.html
│   │   └── itm_otm.html
│   │
│   ├── static/
│   │   ├── css/
│   │   │   └── style.css
│   │   │
│   │   ├── js/
│   │   │   ├── atm.js
│   │   │   └── itm_otm.js
│   │
│   └── data/
│       └── oi_data.db
│
├── requirements.txt
├── run.bat
└── README.md

commands:
uvicorn app.main:app --reload
http://127.0.0.1:8000/dashboardhttp://127.0.0.1:8000/dashboard
http://127.0.0.1:8000/itm
http://127.0.0.1:8000/greeks
http://127.0.0.1:8000/dashboard4
