Atlas Probe 2b Extractor reconciliation patch

Copy these files into 00_RUN_THESE_FILES:

1. Atlas_Probe2b_Extractor.py
2. Run_Atlas_Probe2b_Extractor.bat

What changed:

- The extractor now looks for ATLAS_RECONCILIATION_DECISIONS.xlsx automatically.
- It searches the Atlas output folder you choose and the reports subfolder.
- It applies KEEP / EXCLUDE / REMAP before Probe 2b and Stage 4 extraction.
- It writes ATLAS_RECONCILIATION_DECISIONS_APPLIED.csv in the extractor output
  folder so you can audit what happened.

Where to put the completed workbook:

Best:
03_ATLAS_OUTPUTS\ATLAS_RECONCILIATION_DECISIONS.xlsx

Also accepted:
03_ATLAS_OUTPUTS\reports\ATLAS_RECONCILIATION_DECISIONS.xlsx

Important:

The extractor will not ask you where the reconciliation workbook is. It finds it
from the Atlas output folder you select.

When you run the extractor, choose the Atlas output folder:

03_ATLAS_OUTPUTS

Do not choose:

03_ATLAS_OUTPUTS\reports

The extractor needs access to both reports and the Atlas cache.
