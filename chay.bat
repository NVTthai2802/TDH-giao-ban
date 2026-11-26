@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" goto run

set PY=
py -3.13 -c "import sys" >nul 2>nul && set "PY=py -3.13"
if not defined PY py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY goto nopython

echo Lan dau chay: dang cai thu vien, mat vai phut...
%PY% -m venv .venv
if errorlevel 1 goto nopython
if not exist wheels goto online
".venv\Scripts\python.exe" -m pip install --no-index --find-links wheels -r requirements.txt
if not errorlevel 1 goto run
echo Cai tu thu muc wheels khong duoc, co the khac phien ban Python. Thu cai qua Internet...

:online
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto fail

:run
".venv\Scripts\python.exe" app.py
pause
exit /b 0

:nopython
echo.
echo Chua cai duoc Python cho phan mem nay.
echo Tai Python 3.13 tai https://www.python.org/downloads/ va tich o "Add python.exe to PATH" khi cai.
echo Neu vua cai xong, dong cua so nay roi mo lai chay.bat.
if exist .venv rmdir /s /q .venv
pause
exit /b 1

:fail
echo.
echo Cai thu vien that bai. Kiem tra thu muc wheels co du file, hoac noi Internet roi thu lai.
rmdir /s /q .venv
pause
exit /b 1
