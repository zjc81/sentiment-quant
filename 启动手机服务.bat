@echo off
cd /d "%~dp0"
set PYTHON_EXE=C://Users//Think//.workbuddy//binaries//python//envs//sentiment_quant//Scripts//python.exe/r/necho ===================================================
echo   SentimentQuant Mobile Server
echo ===================================================
echo.
echo Starting Flask server...
echo.
"%PYTHON_EXE%" mobile_app.py
pause
