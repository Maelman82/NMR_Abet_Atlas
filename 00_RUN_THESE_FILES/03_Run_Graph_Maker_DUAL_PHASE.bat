@echo off
setlocal
cd /d "%~dp0"
title ATLAS CPT - Stage4 and Probe2b ITI Graphs
where py >nul 2>nul
if not errorlevel 1 (
  py -3 -c "import pandas,numpy,matplotlib,scipy" >nul 2>nul
  if not errorlevel 1 (
    py -3 "%~dp0ATLAS_Dual_Phase_Graph_Maker.py"
    goto done
  )
)
where python >nul 2>nul
if not errorlevel 1 (
  python -c "import pandas,numpy,matplotlib,scipy" >nul 2>nul
  if not errorlevel 1 (
    python "%~dp0ATLAS_Dual_Phase_Graph_Maker.py"
    goto done
  )
)
echo ERROR: Python 3 or required packages unavailable.
echo Install: py -3 -m pip install pandas numpy matplotlib scipy
:done
if errorlevel 1 echo Graph Maker failed. Check the error above.
pause
endlocal
