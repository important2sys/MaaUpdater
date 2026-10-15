@echo off
rem ===========================================================================
rem  ghupdate GUI launcher
rem
rem  managed Python (3.13.x) ships without Tcl/Tk, so tkinter is unavailable
rem  there. This launcher probes for an interpreter that CAN import tkinter and
rem  uses the first one that works -- so upgrading Python later needs no edit.
rem
rem  Probe order:
rem    1. %%MAAUPD_PYTHON%%                          (manual override)
rem    2. %%LOCALAPPDATA%%\Programs\Python\Python3*\  (python.org installer)
rem    3. %%APPDATA%%\uv\python\cpython-*\            (uv-managed)
rem    4. whatever `where` finds on PATH
rem
rem  Pass --debug to keep a console window (see ghupdate-gui-debug.bat).
rem  ASCII only on purpose: non-ASCII in a .bat breaks cmd parsing when the
rem  active code page is not UTF-8. All user-facing text is printed by Python.
rem ===========================================================================

setlocal EnableExtensions
set "HERE=%~dp0"
set "APP=%HERE%gui\app.py"
set "MODE=%~1"
set "EXE=pythonw.exe"
if /i "%MODE%"=="--debug" set "EXE=python.exe"

set "PY="

call :try "%MAAUPD_PYTHON%"

if not defined PY (
  for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
    if not defined PY call :try "%%~fD\%EXE%"
  )
)

if not defined PY (
  for /d %%D in ("%APPDATA%\uv\python\cpython-*") do (
    if not defined PY call :try "%%~fD\%EXE%"
  )
)

if not defined PY (
  for /f "delims=" %%P in ('where %EXE% 2^>nul') do (
    if not defined PY call :try "%%P"
  )
)

if not defined PY goto :nopython

"%PY%" "%APP%" %MODE%
set "RC=%ERRORLEVEL%"

if /i "%MODE%"=="--debug" (
  echo.
  echo [ghupdate] python exited with code %RC%
  pause
)
exit /b %RC%


:try
rem Use the first candidate that can import tkinter.
if defined PY goto :eof
if "%~1"=="" goto :eof
if not exist "%~1" goto :eof
"%~1" -c "import tkinter" >nul 2>nul
if errorlevel 1 goto :eof
set "PY=%~1"
goto :eof


:nopython
echo.
echo  [ghupdate] No Python interpreter with tkinter was found.
echo.
echo  Probed, in order:
echo    1. MAAUPD_PYTHON                 = %MAAUPD_PYTHON%
echo    2. %LOCALAPPDATA%\Programs\Python\Python3*\
echo    3. %APPDATA%\uv\python\cpython-*\
echo    4. %EXE% found on PATH
echo.
echo  How to fix:
echo    - Install Python from python.org (tcl/tk is bundled by default), or
echo    - set MAAUPD_PYTHON to a pythonw.exe that has tkinter, e.g.
echo        setx MAAUPD_PYTHON "C:\Path\To\Python314\pythonw.exe"
echo.
echo  The command line interface does not need tkinter and still works:
echo    update-all.bat
echo.
pause
exit /b 3
