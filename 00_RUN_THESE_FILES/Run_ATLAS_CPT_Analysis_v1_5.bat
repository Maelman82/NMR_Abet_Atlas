@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo ==========================================
echo   ATLAS CPT Analysis Module v1.5
echo ==========================================
echo.

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYEXE=py"
    set "PYARG=-3"
) else (
    set "PYEXE=python"
    set "PYARG="
)

echo Checking required Python packages...
%PYEXE% %PYARG% -c "import numpy, pandas, scipy, statsmodels, patsy, openpyxl" >nul 2>nul
if errorlevel 1 (
    echo.
    echo Installing missing analysis packages...
    %PYEXE% %PYARG% -m pip install --user numpy pandas scipy statsmodels patsy openpyxl
    if errorlevel 1 (
        echo.
        echo Automatic package installation failed.
        echo Please run:
        echo %PYEXE% %PYARG% -m pip install --user numpy pandas scipy statsmodels patsy openpyxl
        echo.
        pause
        exit /b 1
    )
)

echo.
echo Dependencies are ready. Starting analysis...
echo.

%PYEXE% %PYARG% "ATLAS_CPT_Analysis_Module_v1_5.py"

if errorlevel 1 (
    echo.
    echo Analysis module stopped with an error.
    pause
    exit /b 1
)

echo.
echo Analysis completed successfully.
pause
endlocal
