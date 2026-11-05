@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Dual Phase Extractor - Diagnostics
set "LOG=%~dp002_Run_Dual_Phase_Extractor_RUN_LOG.txt"
>"%LOG%" echo Dual Phase Extractor startup checks
 echo ================================
 echo  Dual Phase Extractor
 echo ================================
 echo Folder: %CD%
 echo Log: %LOG%
 echo.
if not exist "%~dp0ATLAS_Dual_Phase_Extractor.py" ( echo MISSING: ATLAS_Dual_Phase_Extractor.py & goto :failed )
set "PYTHON_CMD="
py -3 -c "import sys; assert sys.version_info.major==3" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  python -c "import sys; assert sys.version_info.major==3" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (echo ERROR: Python 3 not found. & goto :failed)
echo Python command: %PYTHON_CMD%
%PYTHON_CMD% -c "import openpyxl" >>"%LOG%" 2>&1
if errorlevel 1 (
 echo ERROR: Missing Python dependency. See run log.
 echo Install required Python packages into the SAME Python environment.
 goto :failed
)
echo Starting ATLAS_Dual_Phase_Extractor.py ...
%PYTHON_CMD% -u "%~dp0ATLAS_Dual_Phase_Extractor.py" %* 
set "RC=%errorlevel%"
>>"%LOG%" echo Process exit code: %RC%
if not "%RC%"=="0" goto :failed
echo Completed successfully.
goto :done
:failed
echo.
echo FAILED. Check the above error and %LOG%.
:done
echo.
pause
endlocal
