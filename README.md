# NMR ABET Atlas

Python tools for indexing ABET touchscreen databases, reviewing session and animal metadata, extracting CPT/Probe 2b trials and matched Stage 4 baselines, and producing figures.

This is a source-code snapshot of the current desktop workflow. No research databases, animal metadata, decisions, results, or figures are included.

## Requirements

Windows is the primary desktop workflow. Python 3.13 is the environment used to check this snapshot; the code uses Python 3.10+ syntax, but other versions have not been checked. Install Python with Tkinter and the Python launcher for the graphical interfaces and Windows launchers.

From the repository folder, install the dependencies into the same Python environment used to launch the tools:

```console
py -3 -m pip install -r requirements.txt
```

The requirements record versions found in the source environment. This snapshot has not been independently validated in a clean environment.

`abet-converter` is used for Access-style ABET databases. Native SQLite databases use Python's built-in SQLite support. Conversion errors are reported by the Atlas; installation and compatibility of the converter may require additional setup for the database being used.

## Desktop workflow

Keep `atlas_core` beside `NMR_ABET_Atlas.py`, and keep both graph-maker scripts together inside `00_RUN_THESE_FILES`.

1. Run `00_RUN_THESE_FILES/01_Run_Atlas_QC.bat`. Select the database folder and an Atlas output folder. Optional inputs include an animal metadata CSV, reconciliation decisions, and separate final Probe session QC decisions.
2. Review the reports and resolve animal/session selection decisions before analysis. Rebuild or reapply decisions as appropriate. The separate final Probe QC file is used to create `ATLAS_SESSION_MASTER_FINAL.csv`; it is distinct from animal reconciliation decisions.
3. Run `00_RUN_THESE_FILES/02_Run_Dual_Phase_Extractor.bat`. Select the Atlas folder containing `reports/` and `cache/`. An optional session-selection CSV/XLSX can specify sessions to extract. Review the generated QC and session-selection outputs.
4. Run `00_RUN_THESE_FILES/03_Run_Graph_Maker_DUAL_PHASE.bat` and select the extractor's output folder.

Do not assume that an output is analysis-ready simply because a script completed. Review QC reports and the selection/exclusion rules for your study.

See [the extractor notes](00_RUN_THESE_FILES/README_DUAL_PHASE_EXTRACTOR.txt) for export filenames and baseline behavior. Older desktop instructions referencing `Run_NMR_ABET_Atlas.bat`, `Create_ATLAS_RECONCILIATION_DECISIONS.py`, or `Run_Atlas_Probe2b_Extractor.bat` describe a different layout; those files are not part of this snapshot.

## Command-line usage

Run from the repository folder. Replace the example paths with your own local folders.

```console
py -3 00_RUN_THESE_FILES/NMR_ABET_Atlas.py --input "path/to/databases" --output "path/to/atlas-output" --workers 6 --no-gui
py -3 00_RUN_THESE_FILES/ATLAS_Dual_Phase_Extractor.py --atlas "path/to/atlas-output" --output "path/to/extracted-output"
py -3 00_RUN_THESE_FILES/ATLAS_Dual_Phase_Graph_Maker.py --help
```

Use `--help` with each script for its supported arguments. Launching without arguments opens the graphical workflow where supported.

## Inputs and outputs

The indexer scans `.ABETdb`, `.mdb`, `.db`, `.sqlite`, and `.sqlite3` files directly inside the selected input folder. Expected source tables include `tbl_Schedules`, `tbl_Schedule_Notes`, and `tbl_Data`.

Optional metadata columns include `AnimalID`, `Project_Group`, `Cohort`, `Timepoint_Label`, `Sex`, `Genotype`, `Treatment`, and `Strain`. Actual metadata must be supplied locally.

The Atlas creates cached databases and reports. The extractor produces trial/session metrics and QC reports; graph makers consume those exports. Keep these generated files outside the source repository.

## Scope and analysis assumptions

The indexing layer records sessions, while trial reconstruction currently targets the observed CPT `Display Image` event pattern. Other schedules may be indexed without yielding reconstructed trials.

The extractor and graph makers contain study-specific logic, including Lecanemab/Vaccine project labels, KI2TA-3/KI2TA-4 groups, timepoint and eligibility rules, treatment exclusions, and Stage 4 baseline/session-selection conventions. Review and adapt these before applying the code to a different study. These labels are code configuration, not included animal records.

This snapshot is shared for review and reproducibility. Startup checks do not establish scientific validity, correctness for every ABET schedule, or agreement with a complete dataset.

## Sharing and licensing

Only source code, launchers, and documentation belong in this repository. The supplied `.gitignore` excludes common research-data, cache, output, and credential file types; it is an additional safeguard, not a substitute for reviewing uploads.

No license has been selected for this prepared snapshot. Public visibility alone does not grant an open-source license. The code owner should select an appropriate license and confirm any institutional or third-party requirements before release.
