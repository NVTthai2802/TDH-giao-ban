@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo === Dong goi phan mem thanh file KeHoachXa.exe ===
echo Lam tren may cua ban (co Internet), mot lan. May khach khong can cai Python.
echo.
set PY=
py -3.13 -c "import sys" >nul 2>nul && set "PY=py -3.13"
if not defined PY py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY goto nopython

if exist ".venv-build\Scripts\python.exe" goto deps
%PY% -m venv .venv-build
if errorlevel 1 goto nopython

:deps
set B=.venv-build\Scripts\python.exe
if exist wheels "%B%" -m pip install -q --no-index --find-links wheels -r requirements.txt
if errorlevel 1 "%B%" -m pip install -q -r requirements.txt
if not exist wheels "%B%" -m pip install -q -r requirements.txt
"%B%" -m pip install -q pyinstaller
if errorlevel 1 goto fail
"%B%" tools\build_exe.py
if errorlevel 1 goto fail
echo.
echo Chep NGUYEN thu muc dist\KeHoachXa sang may khach (nen thanh .zip roi giai nen ben kia).
echo Tren may khach: nhan dup KeHoachXa.exe
pause
exit /b 0

:nopython
echo.
echo Khong tim thay Python chay duoc tren may nay.
echo Cai Python 3.13 tai https://www.python.org/downloads/ va tich o "Add python.exe to PATH".
pause
exit /b 1

:fail
echo.
echo Dong goi that bai. Chup dong loi cuoi cung gui lai de sua.
pause
exit /b 1
