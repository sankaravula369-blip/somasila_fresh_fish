@echo off
setlocal

set "PROJECT_DIR=%~dp0"
set "APP_DIR=%PROJECT_DIR%python"
if not defined PORT set "PORT=5000"
if not defined DATABASE_PATH set "DATABASE_PATH=%APP_DIR%\data\sff.db"

if not defined PYTHON (
    if exist "%APP_DIR%\.venv\Scripts\python.exe" (
        set "PYTHON=%APP_DIR%\.venv\Scripts\python.exe"
        set "PYTHON_ARGS="
    ) else (
        where py >nul 2>&1
        if not errorlevel 1 (
            set "PYTHON=py"
            set "PYTHON_ARGS=-3"
        ) else (
            where python >nul 2>&1
            if errorlevel 1 (
                echo ERROR: Python was not found. Install Python and add it to PATH.
                pause
                exit /b 1
            )
            set "PYTHON=python"
            set "PYTHON_ARGS="
        )
    )
)

powershell -NoProfile -Command "$client = New-Object System.Net.Sockets.TcpClient; try { $client.Connect('127.0.0.1', %PORT%); exit 0 } catch { exit 1 } finally { $client.Dispose() }" >nul 2>&1
if not errorlevel 1 (
    echo ERROR: Port %PORT% is already in use.
    echo Find the process with: netstat -ano ^| findstr :%PORT%
    echo Stop that process from Task Manager, or close the other Flask server window.
    echo Then run start_server.bat again.
    pause
    exit /b 1
)

if not exist "%APP_DIR%\app.py" (
    echo ERROR: Flask app was not found at "%APP_DIR%\app.py".
    pause
    exit /b 1
)

if not defined OWNER_WHATSAPP_NUMBER (
    set /p "OWNER_WHATSAPP_NUMBER=Enter owner WhatsApp number with country code, digits only: "
)

"%PYTHON%" %PYTHON_ARGS% -c "import os,re,sys; sys.exit(0 if re.fullmatch(r'[1-9][0-9]{7,14}', os.environ.get('OWNER_WHATSAPP_NUMBER','')) else 1)" >nul 2>&1
if errorlevel 1 (
    echo ERROR: OWNER_WHATSAPP_NUMBER is missing or invalid.
    echo Enter digits only, including the country calling code, for example 91 followed by the mobile number.
    echo Do not include a plus sign, spaces, or dashes.
    pause
    exit /b 1
)

"%PYTHON%" %PYTHON_ARGS% -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo ERROR: Flask or another required package is missing.
    echo Install dependencies by running:
    echo   "%PYTHON%" %PYTHON_ARGS% -m pip install -r "%APP_DIR%\requirements.txt"
    pause
    exit /b 1
)

pushd "%APP_DIR%"
echo Starting SFF on http://127.0.0.1:%PORT%
echo For phone access on the same Wi-Fi, use http://YOUR-LAPTOP-IP:%PORT%
echo Stop with Ctrl+C. Restart by stopping this window and running start_server.bat again.
"%PYTHON%" %PYTHON_ARGS% app.py
set "SERVER_EXIT=%ERRORLEVEL%"
popd

if not "%SERVER_EXIT%"=="0" (
    echo.
    echo SFF stopped with exit code %SERVER_EXIT%.
    echo If port %PORT% is occupied, run: netstat -ano ^| findstr :%PORT%
    pause
)

exit /b %SERVER_EXIT%
