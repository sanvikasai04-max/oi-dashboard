# Mobile / Remote Dashboard Access

Use these steps when you want to open the OI dashboard from mobile or any other device, even when that device is on a different Wi-Fi/network.

## Important URLs

Local PC URLs:

```text
ATM Dashboard: http://127.0.0.1:8000/dashboard
ITM Dashboard: http://127.0.0.1:8000/itm
```

Remote/mobile URLs using the fixed ngrok domain:

```text
ATM Dashboard: https://insessorial-tess-unlean.ngrok-free.dev/dashboard
ITM Dashboard: https://insessorial-tess-unlean.ngrok-free.dev/itm
```

## Prerequisites

1. Python virtual environment should already exist in `venv`.
2. Project dependencies should be installed:

```powershell
pip install -r requirements.txt
```

3. ngrok should be installed on the local PC.
4. ngrok account should be verified.
5. ngrok authtoken should be added one time:

```powershell
ngrok config add-authtoken YOUR_TOKEN_HERE
```

Get the token from:

```text
https://dashboard.ngrok.com/get-started/your-authtoken
```

Do not share the ngrok authtoken with anyone.

## Step 1: Start Dashboard On Local PC

Open PowerShell on the local PC and run:

```powershell
cd "C:\Users\Vidya sagar\OneDrive\Desktop\myscripts\htmldashboard\oi-dashboard"
venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Keep this PowerShell window open.

Check locally:

```text
http://127.0.0.1:8000/dashboard
http://127.0.0.1:8000/itm
```

## Step 2: Start ngrok Tunnel

Open a second PowerShell window on the local PC and run:

```powershell
ngrok http --domain=insessorial-tess-unlean.ngrok-free.dev 8000
```

Keep this PowerShell window open too.

ngrok should show:

```text
Forwarding  https://insessorial-tess-unlean.ngrok-free.dev -> http://localhost:8000
```

## Step 3: Open From Mobile Or Any Device

On mobile browser, open:

```text
https://insessorial-tess-unlean.ngrok-free.dev/dashboard
```

or:

```text
https://insessorial-tess-unlean.ngrok-free.dev/itm
```

The mobile/device can be on a different Wi-Fi or mobile data.

## If ngrok Shows A Warning Page

On a new mobile/browser, ngrok may show a warning page first.

Tap:

```text
Visit Site
```

Then wait a few seconds. If it does not respond, try:

1. Chrome incognito mode.
2. Another browser.
3. Disable VPN/ad blocker/private DNS temporarily.
4. Refresh the page.

## Daily Usage

Every day, you can use the automated script:

```powershell
run_mobile.bat
```

This opens two terminal windows automatically:

1. FastAPI dashboard on port `8000`.
2. ngrok fixed-domain tunnel.

Keep both opened terminal windows running.

Then use:

```text
ATM: https://insessorial-tess-unlean.ngrok-free.dev/dashboard
ITM: https://insessorial-tess-unlean.ngrok-free.dev/itm
```

Manual option:

Run these two commands in two separate PowerShell windows.

PowerShell 1:

```powershell
cd "C:\Users\Vidya sagar\OneDrive\Desktop\myscripts\htmldashboard\oi-dashboard"
venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

PowerShell 2:

```powershell
ngrok http --domain=insessorial-tess-unlean.ngrok-free.dev 8000
```

Then use:

```text
ATM: https://insessorial-tess-unlean.ngrok-free.dev/dashboard
ITM: https://insessorial-tess-unlean.ngrok-free.dev/itm
```

## Notes And Precautions

1. Both PowerShell windows must remain open.
2. If the dashboard does not open locally, mobile access will not work.
3. If the ngrok tunnel is stopped, mobile access will stop.
4. Anyone with the ngrok URL can open the dashboard, so do not share the link publicly.
5. Do not expose API tokens, access tokens, or trading credentials in the dashboard.
6. This project uses FastAPI, so use `uvicorn`, not Flask.
7. The app path is:

```text
app.main:app
```

8. The app port used for this dashboard is:

```text
8000
```

9. If you do not use the fixed domain command, normal `ngrok http 8000` may generate a different URL after restart.
