@echo off
setlocal
pushd "%~dp0" || exit /b 1
title AgriSense
set "VENV=.venv"
set "PYTHON=%VENV%\Scripts\python.exe"

if exist "%PYTHON%" (
    "%PYTHON%" -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
    if not errorlevel 1 goto dependencies
    echo The local Python environment cannot run on this PC.
    echo Extract a fresh copy of AgriSense from the ZIP and try again.
    goto failed
)

echo Setting up AgriSense for this PC...
py -3.12 -c "import sys" >nul 2>&1
if not errorlevel 1 (
    py -3.12 -m venv "%VENV%" || goto failed
    goto dependencies
)
python -c "import sys; assert sys.version_info[:2] == (3, 12)" >nul 2>&1
if errorlevel 1 (
    echo Install Python 3.12 for Windows from python.org and enable Add Python to PATH.
    echo Then double-click this launcher again.
    goto failed
)
python -m venv "%VENV%" || goto failed

:dependencies
if not exist "%VENV%\agrisense-ready" (
    echo Installing AgriSense packages. An internet connection is needed for this step.
    "%PYTHON%" -m pip install -r requirements.txt || goto failed
    type nul > "%VENV%\agrisense-ready"
)

echo Starting AgriSense at http://localhost:8501
echo Keep this window open while using the app. Press Ctrl+C here to stop it.
"%PYTHON%" -m streamlit run app.py --server.address localhost --server.port 8501 --server.headless false --browser.gatherUsageStats false
if errorlevel 1 goto failed
popd
exit /b 0

:failed
echo.
echo AgriSense setup or startup stopped. See the message above.
pause
popd
exit /b 1
