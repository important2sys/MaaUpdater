@echo off
rem ============================================================
rem  run-maaend.bat  -  launch MaaEnd with on-demand GitHub mirror
rem
rem  Same idea as run-maa.bat. MaaEnd is built on reqwest and
rem  reads HTTP_PROXY / HTTPS_PROXY from the environment, so no
rem  config file needs to be edited at all.
rem ============================================================
setlocal
cd /d "%~dp0"

set "PORT=8899"
set "APP=D:\RL\MaaEnd-win-x86_64-v2.23.0\MaaEnd.exe"

if not exist "%APP%" goto no_app

echo [1/4] starting local mirror proxy ...
call "%~dp0ghproxy-ctl.bat" start
if errorlevel 1 goto ctl_failed

echo [2/4] pointing MaaEnd at 127.0.0.1:%PORT% (env vars only, config file untouched)
set "HTTP_PROXY=http://127.0.0.1:%PORT%"
set "HTTPS_PROXY=http://127.0.0.1:%PORT%"
set "ALL_PROXY=http://127.0.0.1:%PORT%"
set "NO_PROXY=localhost,127.0.0.1"

echo [3/4] launching MaaEnd ...
start "" /wait "%APP%"

echo [4/4] MaaEnd closed, cleaning up ...
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
