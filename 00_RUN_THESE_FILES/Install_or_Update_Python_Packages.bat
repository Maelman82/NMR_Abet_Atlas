@echo off
setlocal EnableExtensions
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    set "PYEXE=py"
    set "PYARG=-3"
) else (
    set "PYEXE=python"
    set "PYARG="
)

echo Installing/updating required Python packages for NMR ABET Atlas...
echo.
%PYEXE% %PYARG% -m pip install --user -r requirements.txt

if errorlevel 1 (
    echo.
    echo Package installation failed.
    echo If this is a work-computer permissions issue, send me a screenshot of this window.
    pause
    exit /b 1
)

echo.
echo Python packages are ready.
pause
endlocal
