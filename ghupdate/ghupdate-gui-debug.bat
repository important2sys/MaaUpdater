@echo off
rem ===========================================================================
rem  ghupdate GUI launcher -- debug variant.
rem
rem  Uses python.exe instead of pythonw.exe, so the console stays and you can
rem  see tracebacks. The launcher also pauses afterwards to show the exit code.
rem  Use this when the window does not appear or closes immediately.
rem
rem  Crash details are also appended to ghupdate\gui-error.log either way.
rem ===========================================================================

call "%~dp0ghupdate-gui.bat" --debug
exit /b %ERRORLEVEL%
