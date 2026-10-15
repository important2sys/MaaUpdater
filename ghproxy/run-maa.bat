@echo off
rem ============================================================
rem  run-maa.bat  -  launch MAA with on-demand GitHub mirror
rem
rem  Flow:  install CA -> start proxy -> launch MAA -> on exit
rem         stop proxy -> remove CA
rem  Nothing is left behind when MAA closes.
rem ============================================================
setlocal
cd /d "%~dp0"

set "PORT=8899"
set "APP=D:\RL\MAA-v6.9.5-win-x64\MAA.exe"

if not exist "%APP%" goto no_app

echo [1/4] starting local mirror proxy ...
call "%~dp0ghproxy-ctl.bat" start
if errorlevel 1 goto ctl_failed

echo [2/4] pointing MAA at 127.0.0.1:%PORT% (env vars only, config file untouched)
set "HTTP_PROXY=http://127.0.0.1:%PORT%"
set "HTTPS_PROXY=http://127.0.0.1:%PORT%"
set "NO_PROXY=localhost,127.0.0.1"

echo [3/4] launching MAA ...
start "" /wait "%APP%"

echo [4/4] MAA closed, cleaning up ...
call "%~dp0ghproxy-ctl.bat" stop
echo [OK] done - proxy stopped and CA removed
pause
exit /b 0

:no_app
echo [ERROR] not found: %APP%
pause
exit /b 1

:ctl_failed
echo [ERROR] proxy start failed
pause
exit /b 1
