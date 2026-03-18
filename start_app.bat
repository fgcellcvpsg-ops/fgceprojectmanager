@echo off
cd /d "%~dp0"
echo ========================================================
echo   KHOI CHAY DU AN FGCE PROJECT MANAGER
echo ========================================================

if not exist .venv (
    echo [LOI] Khong tim thay moi truong ao .venv
    echo Vui long chay file install_dependencies.bat truoc.
    pause
    exit /b
)

call .venv\Scripts\activate.bat

echo Dang khoi dong server...
echo Truy cap vao: http://127.0.0.1:5001
echo Nhan Ctrl+C de dung server.
echo.

.venv\Scripts\python.exe run.py
if errorlevel 1 pause
