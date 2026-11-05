ATLAS DUAL PHASE EXTRACTOR - Stage 4 and Probe 2b
================================================
1. Place the .bat and .py together in the Atlas launcher folder.
2. Double-click 02_Run_Dual_Phase_Extractor.bat.
3. Choose the Atlas output folder, and optionally the output CSV folder and Probe 2b session selection file.
4. When done, point 03_Run_Graph_Maker_DUAL_PHASE.bat at the SAME output CSV folder.

Graph Maker required inputs, same folder:
  Probe 2b: CPT_67_COLUMN_ALL_DATABASES.csv + PROBE2B_TRIAL_MASTER.csv
  Stage 4: STAGE4_BASELINE_SESSION_METRICS_BY_ITI.csv + STAGE4_BASELINE_WITHIN_SESSION_DECILES_BY_ITI.csv

Extra compatibility exports (Probe 2b):
  CPT_49_COLUMN_ALL_DATABASES.csv (ITI pooled)
  CPT_49_COLUMN_ALL_DATABASES_BY_ITI.csv (50 columns including ITI)
  CPT_67_COLUMN_ALL_DATABASES.csv (ITI pooled)
  CPT_67_COLUMN_ALL_DATABASES_BY_ITI.csv (68 columns including ITI)

Extra compatibility exports (Stage 4 baseline):
  STAGE4_CPT_49_COLUMN_ALL_DATABASES.csv (ITI pooled)
  STAGE4_CPT_49_COLUMN_ALL_DATABASES_BY_ITI.csv (50 columns)
  STAGE4_CPT_67_COLUMN_ALL_DATABASES.csv (ITI pooled)
  STAGE4_CPT_67_COLUMN_ALL_DATABASES_BY_ITI.csv (68 columns)

Stage 4 uses last UP TO four sessions immediately preceding each Probe 2b timepoint, after the preceding Probe 2b block. Partial baselines are marked in STAGE4_BASELINE_QC.csv. Stage 4 has fixed 2-second SD; other SD values remain blank.

A successful synthetic Stage 4 test verified both ITI summary outputs and generated 3 Stage 4 example PDFs with the existing Dual Phase Graph Maker. This is NOT a validation against your full Atlas databases, and Probe 2b graph compatibility relies on its existing graph runner.
