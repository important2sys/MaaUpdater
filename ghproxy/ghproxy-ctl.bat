@echo off
rem ============================================================
rem  ghproxy-ctl.bat - start / stop the on-demand GitHub mirror proxy
rem
rem  Usage:
rem    ghproxy-ctl.bat start       install CA + start proxy
rem    ghproxy-ctl.bat stop        stop proxy + remove CA
rem    ghproxy-ctl.bat status      show current state
rem    ghproxy-ctl.bat install-ca  install CA only
rem    ghproxy-ctl.bat remove-ca   remove CA only
rem
rem  NOTE: installing a CA into CurrentUser\Root may pop up a
rem        Windows security warning. Click "Yes" to continue.
rem ============================================================
setlocal
cd /d "%~dp0"

set "PORT=8899"
set "CA_FILE=certs\ghmirror-ca.crt"
set "THUMB_FILE=certs\ca.thumbprint.txt"
set "FLAG=ca_installed.flag"
set "PIDF=ghproxy.pid"

if "%~1"=="" goto usage
if /i "%~1"=="start"      goto do_start
if /i "%~1"=="stop"       goto do_stop
if /i "%~1"=="status"     goto do_status
if /i "%~1"=="install-ca" goto do_install_ca
if /i "%~1"=="remove-ca"  goto do_remove_ca
goto usage

rem ------------------------------------------------------------
rem  locate a usable python (single token, may contain spaces)
rem ------------------------------------------------------------
:find_py
set "PY="
py -c "import ssl" >nul 2>nul
if not errorlevel 1 set "PY=py"
if not defined PY python -c "import ssl" >nul 2>nul
if not defined PY if not errorlevel 1 set "PY=python"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not defined PY if exist "C:\Users\33974\.workbuddy\binaries\python\versions\3.13.12\python.exe" set "PY=C:\Users\33974\.workbuddy\binaries\python\versions\3.13.12\python.exe"
exit /b 0

rem ------------------------------------------------------------
:do_install_ca
if not exist "%CA_FILE%" echo [ERROR] missing "%CA_FILE%"
if not exist "%CA_FILE%" exit /b 1
certutil -addstore -f -user Root "%CA_FILE%" >nul
if errorlevel 1 echo [ERROR] certutil install failed
if errorlevel 1 exit /b 1
set "THUMB="
if exist "%THUMB_FILE%" set /p THUMB=<"%THUMB_FILE%"
if not defined THUMB echo [WARN] thumbprint file missing, "stop" may need manual cleanup
if defined THUMB >"%FLAG%" echo %THUMB%
echo [OK] CA installed into CurrentUser\Root
exit /b 0

rem ------------------------------------------------------------
:do_remove_ca
call :remove_ca_impl
echo [OK] CA removed from CurrentUser\Root
exit /b 0

:remove_ca_impl
set "THUMB="
if exist "%FLAG%" set /p THUMB=<"%FLAG%"
if not defined THUMB if exist "%THUMB_FILE%" set /p THUMB=<"%THUMB_FILE%"
if defined THUMB certutil -delstore -user Root %THUMB% >nul 2>nul
if exist "%FLAG%" del /q "%FLAG%" >nul 2>nul
exit /b 0

rem ------------------------------------------------------------
:do_start
call :find_py
if not defined PY echo [ERROR] no usable python found
if not defined PY exit /b 1
if not exist "ghproxy.py" echo [ERROR] ghproxy.py not found
if not exist "ghproxy.py" exit /b 1

if not exist "%FLAG%" call "%~f0" install-ca
if not exist "%FLAG%" echo [ERROR] CA not installed, aborting
if not exist "%FLAG%" exit /b 1

start "ghproxy" /min "%PY%" "%~dp0ghproxy.py" --port %PORT% --idle-timeout 3600

set /a N=0
:wait_loop
netstat -ano | findstr /r /c:"127.0.0.1:%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 goto ready
set /a N+=1
if %N% GEQ 20 goto start_failed
timeout /t 1 /nobreak >nul
goto wait_loop

:start_failed
echo [ERROR] proxy did not come up on port %PORT%
call "%~f0" stop
exit /b 1

:ready
echo [OK] ghproxy listening on 127.0.0.1:%PORT%  (CA trusted for this session)
exit /b 0

rem ------------------------------------------------------------
:do_stop
set "P="
if exist "%PIDF%" set /p P=<"%PIDF%"
if defined P taskkill /F /PID %P% >nul 2>nul
if exist "%PIDF%" del /q "%PIDF%" >nul 2>nul
call :remove_ca_impl
echo [OK] ghproxy stopped, CA removed
exit /b 0

rem ------------------------------------------------------------
:do_status
netstat -ano | findstr /r /c:"127.0.0.1:%PORT% .*LISTENING" >nul 2>nul
if not errorlevel 1 echo [OK] proxy port %PORT% is OPEN
if errorlevel 1 echo [--] proxy port %PORT% is CLOSED
if exist "%FLAG%" echo [OK] CA flag present - CA is currently installed
if not exist "%FLAG%" echo [--] no CA flag - CA is not installed
exit /b 0

rem ------------------------------------------------------------
:usage
echo ghproxy-ctl.bat start^|stop^|status^|install-ca^|remove-ca
exit /b 1
