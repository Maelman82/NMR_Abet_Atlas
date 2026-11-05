@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Atlas QC - Diagnostics
set "LOG=%~dp001_Run_Atlas_QC_RUN_LOG.txt"
>"%LOG%" echo Atlas QC startup checks
 echo ================================
 echo  Atlas QC
 echo ================================
 echo Folder: %CD%
 echo Log: %LOG%
 echo.
if not exist "%~dp0NMR_ABET_Atlas.py" ( echo MISSING: NMR_ABET_Atlas.py & goto :failed )
set "PYTHON_CMD="
py -3 -c "import sys; assert sys.version_info.major==3" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  python -c "import sys; assert sys.version_info.major==3" >nul 2>nul
  if not errorlevel 1 set "PYTHON_CMD=python"
)
if not defined PYTHON_CMD (echo ERROR: Python 3 not found. & goto :failed)
echo Python command: %PYTHON_CMD%
%PYTHON_CMD% -c "import atlas_core.indexer" >>"%LOG%" 2>&1
if errorlevel 1 (
 echo ERROR: Missing Python dependency. See run log.
 echo Install required Python packages into the SAME Python environment.
 goto :failed
)
echo Starting NMR_ABET_Atlas.py ...
%PYTHON_CMD% -u "%~dp0NMR_ABET_Atlas.py" %* 
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
