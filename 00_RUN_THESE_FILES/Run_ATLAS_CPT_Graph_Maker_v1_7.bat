@echo off
cd /d "%~dp0"

echo ==========================================
echo   ATLAS CPT Graph Maker v1.7
echo ==========================================
echo.

echo Using Python:
python --version
echo.

echo Starting graph maker...
python "ATLAS_CPT_Graph_Maker_v1_7.py"

echo.
echo ------------------------------------------
echo Graph maker finished or stopped.
echo ------------------------------------------
pause