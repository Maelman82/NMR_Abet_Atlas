@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SCRIPT=Atlas_Probe2b_Extractor.py"

if not exist "%SCRIPT%" (
  echo ERROR: %SCRIPT% was not found in:
  echo %CD%
  echo.
  pause
  exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
  py -3 "%SCRIPT%"
  set "RC=%errorlevel%"
  if not "%RC%"=="0" pause
  exit /b %RC%
)

where python >nul 2>nul
if %errorlevel%==0 (
  python "%SCRIPT%"
  set "RC=%errorlevel%"
  if not "%RC%"=="0" pause
  exit /b %RC%
)

echo Python 3 was not found on this computer.
pause
exit /b 1
