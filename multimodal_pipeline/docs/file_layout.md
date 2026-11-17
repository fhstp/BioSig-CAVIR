# Input File Layout and Naming

Audience: users preparing input folders for `run_pipeline`.

## Folder layout

The loader expects a participant folder per ID under `input_path` (default `data`):

```
data_root/
  01/
    TaskA_ECG.csv
    TaskA_GSR.csv
    TaskA_Eyetracking.csv
    TaskA_HEAD_MOVEMENT.csv
  02/
    TaskA_ECG.csv
    TaskB_GSR.csv
```

The exact filenames are flexible, but **must** match the search patterns below.

## Search patterns by modality

The loader (`load_data_file`) uses a glob pattern per modality.

- **ECG**: `*{task}*{modality}*` with `modality="ECG"`
- **GSR**: `*{task}*{modality}*` with `modality="GSR"`
- **Eye-tracking**: `*{task}*{modality}*` with `modality="Eyetracking"`
- **Head movement**: `*HEAD*MOVEMENT*.csv` with `modality="HEAD_MOVEMENT"`

This means the following files will be found:

- `MyTask_ECG_preparsed.csv`
- `subject01_TaskA_GSR.csv`
- `Cavir5_Eyetracking_preparsed.csv`
- `TaskA_HEAD_MOVEMENT.csv`

## Delimiters

CSV is expected by default. If your data is TSV, update the loader call to use `sep="\\t"` or adjust per-modality calls.

## Important notes

- `run_pipeline` checks for `*{task}*_preparsed.csv` in each participant folder.
  - This is only a warning step; modality pipelines still attempt their own searches.
- If multiple files match a pattern, the **first match** is used.
