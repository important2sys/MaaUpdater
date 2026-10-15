@echo off
rem ===========================================================================
rem  ghupdate launcher - MAA / MaaEnd updater via ghfast.top mirror
rem
rem  This file is intentionally ASCII-only. cmd.exe mis-parses UTF-8 batch
rem  files when the code page is switched mid-file, so all Chinese output is
rem  produced by ghupdate.py instead.
rem
rem  Usage:
rem    update-all.bat                   interactive menu
rem    update-all.bat maa     [opts]    update MAA
rem    update-all.bat maaend  [opts]    update MaaEnd
rem    update-all.bat all     [opts]    update both
rem    update-all.bat check             dry-run both
rem ===========================================================================
setlocal
chcp 65001 >nul
title ghupdate - MAA / MaaEnd updater
set "HERE=%~dp0"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

call :find_py
if not defined PY (
  echo [x] Python 3.8+ not found. Install Python, or add its path in :find_py.
  echo.
  pause
  exit /b 1
)

"%PY%" "%HERE%ghupdate.py" %*
set "RC=%ERRORLEVEL%"
endlocal & exit /b %RC%

rem ------------------------------ find python ------------------------------

:find_py
set "PY="
call :try "%USERPROFILE%\.workbuddy\binaries\python\envs\default\Scripts\python.exe"
call :try "%USERPROFILE%\.workbuddy\binaries\python\versions\3.13.12\python.exe"
call :try "%USERPROFILE%\.workbuddy\binaries\python\versions\3.12.0\python.exe"
call :try "%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
call :try "%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
call :try "%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if defined PY exit /b 0
for /f "delims=" %%W in ('where python 2^>nul') do call :try "%%W"
exit /b 0

:try
if defined PY exit /b 0
if not exist "%~1" exit /b 0
"%~1" -c "import sys;raise SystemExit(0 if sys.version_info>=(3,8) else 1)" >nul 2>nul
if not errorlevel 1 set "PY=%~1"
exit /b 0
