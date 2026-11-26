@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0"
echo Tai AI (llama.cpp + mo hinh) - can Internet, chi chay MOT LAN.
echo.
set PY=
if exist "python\python.exe" set "PY=python\python.exe"
if not defined PY py -3.13 -c "import sys" >nul 2>nul && set "PY=py -3.13"
if not defined PY py -3 -c "import sys" >nul 2>nul && set "PY=py -3"
if not defined PY python -c "import sys" >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% tools\chuan_bi_ai.py %*
pause
exit /b 0

:nopython
echo Khong tim thay Python. Tai Python 3.13 tai https://www.python.org/downloads/ va tich o "Add python.exe to PATH" khi cai.
pause
exit /b 1
