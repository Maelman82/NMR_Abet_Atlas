NMR ABET Atlas - 00_RUN_THESE_FILES
===================================

Put this folder here:

  C:\Users\cfodo\Desktop\NMR_ABET_Atlas_v1\00_RUN_THESE_FILES

These files are designed to run from inside this folder. The batch files use:

  cd /d "%~dp0"

That means they automatically switch into the folder where the batch file lives.
They should not care what your old folder path was.

Before the first run on a new computer, double-click:

  Install_or_Update_Python_Packages.bat

That installs/checks the Python packages used by the Atlas builder, extractor,
analysis module, and graph maker.


Recommended folder layout
-------------------------

NMR_ABET_Atlas_v1
  00_RUN_THESE_FILES
  01_DATABASES
    Lecanemab
    Vaccine
  02_METADATA
    Source_Truth
    Reconciliation
  03_ATLAS_OUTPUTS
  04_PROJECT_CPT_DATA
    Lecanemab
    Vaccine
  99_OLD_DO_NOT_USE


What to run
-----------

0. Install_or_Update_Python_Packages.bat
   Run once on a new computer.

1. Run_NMR_ABET_Atlas.bat
   Builds/rebuilds the Atlas from selected ABET databases.

2. Run_Atlas_Probe2b_Extractor.bat
   Pulls Probe 2b and Stage 4 style output from the Atlas.

3. Run_ATLAS_CPT_Analysis_v1_5.bat
   Runs the stats/analysis module.

4. Run_ATLAS_CPT_Graph_Maker_v1_7.bat
   Makes the CPT graph PDFs.


Important
---------

Keep the .bat and .py files together in this folder.

Also keep the atlas_core folder in this folder. NMR_ABET_Atlas.py needs it.

Do not rename the .py files unless you also update the matching .bat file.

The uploaded duplicate names like "(1)", "(2)", and "(3)" were removed in this clean folder because the batch files expect clean filenames.
