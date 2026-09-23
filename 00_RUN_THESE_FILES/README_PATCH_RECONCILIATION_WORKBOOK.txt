NMR ABET Atlas reconciliation workbook patch

Copy these two files into your 00_RUN_THESE_FILES folder:

1. Run_NMR_ABET_Atlas.bat
2. Create_ATLAS_RECONCILIATION_DECISIONS.py

What changes:

- Run_NMR_ABET_Atlas.bat still runs NMR_ABET_Atlas.py with 6 workers.
- If Atlas finishes successfully, it then runs Create_ATLAS_RECONCILIATION_DECISIONS.py.
- The helper looks for:
  - ATLAS_QC_RECONCILIATION*.csv
  - ATLAS_ANIMAL_COVERAGE*.csv
  - ATLAS_ANIMAL_METADATA*.csv if present
- It creates:
  - ATLAS_RECONCILIATION_DECISIONS.xlsx

Where it looks:

- The same folder as the batch/Python files
- ../03_ATLAS_OUTPUTS
- ./03_ATLAS_OUTPUTS
- The current working folder

If ATLAS_RECONCILIATION_DECISIONS.xlsx already exists, the helper moves the old
one to ATLAS_RECONCILIATION_DECISIONS_previous.xlsx before writing a fresh one.

If Excel has the workbook open, close Excel and run the batch file again.
