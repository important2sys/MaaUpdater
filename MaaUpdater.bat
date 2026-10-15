@echo off
rem ===========================================================================
rem  MaaUpdater -- the one and only entry point.
rem
rem  Double-click this file. It opens the graphical updater.
rem
rem  This is a deliberately thin forwarder: all real logic lives in ghupdate\.
rem  Having exactly one double-clickable file in the project root is the whole
rem  point -- the user should never have to guess which of the many scripts to
rem  run.
rem
rem  The target script (ghupdate\ghupdate-gui.bat) probes for a Python
rem  interpreter that can import tkinter and uses the first one that works, so
rem  upgrading Python later needs no edit here. If none is found it prints how
rem  to fix it and reminds you that the command-line entry still works
rem  (ghupdate\update-all.bat).
rem
rem  Usage:
rem    MaaUpdater.bat             open the GUI (default)
rem    MaaUpdater.bat --debug     same, but keep a console window
rem
rem  ASCII only on purpose: non-ASCII bytes in a .bat break cmd.exe parsing when
rem  the active code page is not UTF-8. Every Chinese string the user sees is
rem  printed by Python, never by a .bat file.
rem ===========================================================================

setlocal EnableExtensions
set "HERE=%~dp0"
set "TARGET=%HERE%ghupdate\ghupdate-gui.bat"

if not exist "%TARGET%" (
  echo.
  echo  [x] Cannot find: ghupdate\ghupdate-gui.bat
  echo      Looked in:   "%TARGET%"
  echo.
  echo      Extract the WHOLE folder, not just this one .bat file.
  echo.
  pause
  exit /b 2
)

call "%TARGET%" %*
exit /b %ERRORLEVEL%
