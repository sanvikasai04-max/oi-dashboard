@echo off

echo =====================================
echo Starting OI Dashboard...
echo =====================================

call venv\Scripts\activate

uvicorn app.main:app --reload

pause