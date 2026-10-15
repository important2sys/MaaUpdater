@echo off
rem ============================================================
rem  restore.bat  -  emergency cleanup (idempotent, always safe)
rem
rem  Use this if something crashed and you are not sure whether
rem  the proxy or the local CA is still around. Running it twice
rem  is harmless.
rem ============================================================
setlocal
cd /d "%~dp0"

echo [1/2] stopping proxy (if running) ...
call "%~dp0ghproxy-ctl.bat" stop

echo [2/2] verifying that the CA is really gone ...
call "%~dp0ghproxy-ctl.bat" status

echo.
echo [OK] cleanup finished. Trust store should show no RRL Local Mirror CA.
pause
