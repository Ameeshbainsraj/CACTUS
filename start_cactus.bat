@echo off
title CACTUS AI — Starting...
color 02
cls


echo.
echo  ██████╗ █████╗  ██████╗████████╗██╗   ██╗███████╗
echo  ██╔════╝██╔══██╗██╔════╝╚══██╔══╝██║   ██║██╔════╝
echo  ██║     ███████║██║        ██║   ██║   ██║███████╗
echo  ██║     ██╔══██║██║        ██║   ██║   ██║╚════██║
echo  ╚██████╗██║  ██║╚██████╗   ██║   ╚██████╔╝███████║
echo   ╚═════╝╚═╝  ╚═╝ ╚═════╝   ╚═╝    ╚═════╝ ╚══════╝
echo.
echo         Personal AI Assistant v5.0
echo  -----------------------------------------
echo.


REM ── Python 3.13 path ─────────────────────────────────────────────────────
set PYTHON="C:\Users\amees\AppData\Local\Programs\Python\Python313\python.exe"
set PIP="C:\Users\amees\AppData\Local\Programs\Python\Python313\Scripts\pip.exe"


REM ── Step 1: Check Python ──────────────────────────────────────────────────
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python 3.13 not found at expected path.
    echo [ERROR] Expected: C:\Users\amees\AppData\Local\Programs\Python\Python313\python.exe
    pause
    exit /b 1
)


REM ── Step 2: Install dependencies if missing ───────────────────────────────
echo [CACTUS] Checking dependencies...
%PIP% install python-dotenv SpeechRecognition pyttsx3 pyaudio --quiet --disable-pip-version-check


REM ── Step 3: Fix microphone privacy ───────────────────────────────────────
echo [CACTUS] Granting microphone access...
powershell -Command ^
  "Set-ItemProperty -Path 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\CapabilityAccessManager\ConsentStore\microphone' -Name 'Value' -Value 'Allow' -ErrorAction SilentlyContinue"


REM ── Step 4: Play JARVIS startup theme on Spotify ─────────────────────────
echo [CACTUS] Playing JARVIS startup theme...
powershell -Command "Start-Process 'spotify:search:JARVIS Iron Man startup theme'"
timeout /t 4 /nobreak >nul

REM ── Step 5: Run CACTUS ────────────────────────────────────────────────────
echo [CACTUS] Starting AI core...
echo.
cd /d "%~dp0"
%PYTHON% main.py


REM ── Session ended ─────────────────────────────────────────────────────────
echo.
echo [CACTUS] Session ended.
pause