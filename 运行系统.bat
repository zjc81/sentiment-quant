@echo off
cd /d "%~dp0"
set PYTHON_EXE=C:\Users\Think\.workbuddy\binaries\python\envs\sentiment_quant\Scripts\python.exe
set PIP_EXE=C:\Users\Think\.workbuddy\binaries\python\envs\sentiment_quant\Scripts\pip.exe

echo ===================================================
echo    SentimentQuant System Launcher
echo ===================================================
echo.
echo Select mode:
echo   1. CLI mode
echo   2. GUI mode (recommended)
echo   3. Install/Update dependencies
echo   0. Exit
echo.
set /p CHOICE=Enter option (0-3): 
if "%CHOICE%"=="1" goto CMD_MODE
if "%CHOICE%"=="2" goto GUI_MODE
if "%CHOICE%"=="3" goto INSTALL
if "%CHOICE%"=="0" goto END
goto INVALID

:CMD_MODE
echo.
echo [INFO] Starting CLI mode...
"%PYTHON_EXE%" main.py
pause
goto END

:GUI_MODE
echo.
echo [INFO] Starting GUI mode...
"%PYTHON_EXE%" gui_app.py
pause
goto END

:INSTALL
echo.
echo [INFO] Installing dependencies...
"%PIP_EXE%" install -r requirements.txt
"%PIP_EXE%" install customtkinter
echo.
echo [INFO] Installation complete!
pause
goto END

:INVALID
echo.
echo [ERROR] Invalid option!
pause

:END
