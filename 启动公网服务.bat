@echo off
chcp 65001 >nul
cd /d "%~dp0"

set PYTHON_EXE=C:\Users\Think\.workbuddy\binaries\python\envs\sentiment_quant\Scripts\python.exe
set PYTHONIOENCODING=utf-8

if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found!
    pause
    exit /b 1
)

echo ============================================================
echo   SentimentQuant - 公网模式（手机随时随地访问）
echo ============================================================
echo.
echo   正在启动服务器和公网隧道...
echo.

start "SentimentQuant-Server" "%PYTHON_EXE%" mobile_app.py

:: 等待Flask启动
timeout /t 3 /nobreak >nul

:: 启动公网隧道
echo ============================================================
echo   正在创建公网隧道，请稍候...
echo ============================================================
echo.

"%SYSTEMROOT%\System32\OpenSSH\ssh.exe" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o ServerAliveInterval=30 -o ServerAliveCountMax=3 -R 80:localhost:5000 nokey@localhost.run 2>&1 | findstr /C:"lhr.life"

echo.
echo ============================================================
echo   复制上面的 https://xxxx.lhr.life 到手机浏览器即可
echo   按 Ctrl+C 停止服务
echo ============================================================

pause
