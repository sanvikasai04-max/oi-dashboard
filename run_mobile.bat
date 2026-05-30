@echo off

echo =====================================
echo Starting OI Dashboard for Mobile Access
echo =====================================

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo ERROR: venv not found.
    echo Please create/install the virtual environment first.
    pause
    exit /b 1
)

echo Starting FastAPI dashboard on port 8000...
start "OI Dashboard - Uvicorn" cmd /k "pushd ""%~dp0"" && call venv\Scripts\activate.bat && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

timeout /t 3 /nobreak >nul

echo Starting ngrok tunnel...
start "OI Dashboard - ngrok" cmd /k "ngrok http --domain=insessorial-tess-unlean.ngrok-free.dev 8000"

echo.
echo Local URLs:
echo   ATM: http://127.0.0.1:8000/dashboard
echo   ITM: http://127.0.0.1:8000/itm
echo.
echo Mobile URLs:
echo   ATM: https://insessorial-tess-unlean.ngrok-free.dev/dashboard
echo   ITM: https://insessorial-tess-unlean.ngrok-free.dev/itm
echo.
echo Keep both opened terminal windows running.
echo.
pause
