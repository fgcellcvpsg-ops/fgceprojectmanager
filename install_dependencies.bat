@echo off
cd /d "%~dp0"
echo ========================================================
echo   CAI DAT THU VIEN DU AN FGCE PROJECT MANAGER
echo ========================================================

REM Kiem tra python co duoc cai dat chua
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [LOI] Python chua duoc cai dat hoac chua them vao PATH.
    echo Vui long cai dat Python 3.10 trho len va tich chon "Add Python to PATH".
    pause
    exit /b
)

REM Tao moi truong ao neu chua co
if not exist ".venv" (
    echo Dang tao moi truong ao .venv ...
    python -m venv .venv
) else (
    echo Moi truong ao da ton tai.
)

REM Kich hoat moi truong ao
call .venv\Scripts\activate

REM Nang cap pip
echo Dang nang cap pip...
python -m pip install --upgrade pip

REM Cai dat thu vien tu requirements.txt
if exist "requirements.txt" (
    echo Dang cai dat cac thu vien can thiet...
    pip install -r requirements.txt
    
    REM Cai dat them cac thu vien co the thieu
    pip install Flask-Limiter Flask-SQLAlchemy Flask-Login Flask-Migrate Flask-WTF email-validator
) else (
    echo [CANH BAO] Khong tim thay file requirements.txt.
    echo Dang cai dat cac thu vien mac dinh...
    pip install Flask Flask-SQLAlchemy Flask-Login Flask-Migrate Flask-WTF Flask-Limiter email-validator python-dotenv
)

echo.
echo ========================================================
echo   CAI DAT HOAN TAT!
echo   Ban co the chay file start_app.bat de khoi dong du an.
echo ========================================================
pause
