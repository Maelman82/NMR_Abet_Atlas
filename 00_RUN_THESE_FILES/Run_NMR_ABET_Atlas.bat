@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "SCRIPT=NMR_ABET_Atlas.py"

if not exist "%SCRIPT%" (
  echo ERROR: %SCRIPT% was not found in:
  echo %CD%
  echo.
  pause
  exit /b 1
)

where py >nul 2>nul
if %errorlevel%==0 (
  echo Starting NMR ABET Atlas with default 6 workers...
  py -3 "%SCRIPT%" --workers 6
  set "RC=%errorlevel%"
  if "%RC%"=="0" (
    if exist "Create_ATLAS_RECONCILIATION_DECISIONS.py" (
      echo.
      echo Creating ATLAS_RECONCILIATION_DECISIONS.xlsx with dropdowns...
      py -3 "Create_ATLAS_RECONCILIATION_DECISIONS.py"
      set "RC=%errorlevel%"
    ) else (
      echo.
      echo WARNING: Create_ATLAS_RECONCILIATION_DECISIONS.py was not found.
      echo The Atlas CSV files were created, but the dropdown Excel decision workbook was not.
    )
  )
  if not "%RC%"=="0" pause
  exit /b %RC%
)

where python >nul 2>nul
if %errorlevel%==0 (
  echo Starting NMR ABET Atlas with default 6 workers...
  python "%SCRIPT%" --workers 6
  set "RC=%errorlevel%"
  if "%RC%"=="0" (
    if exist "Create_ATLAS_RECONCILIATION_DECISIONS.py" (
      echo.
      echo Creating ATLAS_RECONCILIATION_DECISIONS.xlsx with dropdowns...
      python "Create_ATLAS_RECONCILIATION_DECISIONS.py"
      set "RC=%errorlevel%"
    ) else (
      echo.
      echo WARNING: Create_ATLAS_RECONCILIATION_DECISIONS.py was not found.
      echo The Atlas CSV files were created, but the dropdown Excel decision workbook was not.
    )
  )
  if not "%RC%"=="0" pause
  exit /b %RC%
)

echo Python 3 was not found on this computer.
pause
exit /b 1
