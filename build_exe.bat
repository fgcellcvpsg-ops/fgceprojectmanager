@echo off
echo Dang don dep thu muc build cu...
rmdir /s /q build
rmdir /s /q dist

echo Dang chay PyInstaller...
python -m PyInstaller --noconfirm FGCEProjectManager.spec

echo Dang copy thu cong cac thu vien thieu...
mkdir "dist\FGCEProjectManager\_internal\flask_limiter"
xcopy /E /Y ".venv\Lib\python3.12\site-packages\flask_limiter" "dist\FGCEProjectManager\_internal\flask_limiter"
if errorlevel 1 echo XCOPY FLASK_LIMITER FAILED

mkdir "dist\FGCEProjectManager\_internal\limits"
xcopy /E /Y ".venv\Lib\python3.12\site-packages\limits" "dist\FGCEProjectManager\_internal\limits"
if errorlevel 1 echo XCOPY LIMITS FAILED

mkdir "dist\FGCEProjectManager\_internal\ordered_set"
xcopy /E /Y ".venv\Lib\python3.12\site-packages\ordered_set" "dist\FGCEProjectManager\_internal\ordered_set"
if errorlevel 1 echo XCOPY ORDERED_SET FAILED

copy /Y ".venv\Lib\python3.12\site-packages\typing_extensions.py" "dist\FGCEProjectManager\_internal\"

echo Dang sao chep cac file cau hinh va du lieu...
copy .env dist\FGCEProjectManager\.env
xcopy /E /I /Y instance dist\FGCEProjectManager\instance

echo.
echo ========================================================
echo Dong goi hoan tat!
echo Chuong trinh nam trong thu muc: dist\FGCEProjectManager
echo Hay copy thu muc 'FGCEProjectManager' sang may khac.
echo Chay file 'FGCEProjectManager.exe' de khoi dong.
echo ========================================================
pause
