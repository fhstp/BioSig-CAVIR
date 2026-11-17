# Troubleshooting

Audience: users debugging missing files, failed sanity checks, or empty outputs.

## No files found for a participant/task

Symptoms:
- `[WARN] No <MODALITY> file found ...` from `load_data_file`.

Checks:
- Verify participant folder exists under `input_path`.
- Verify filename contains both `{task}` and the modality token (e.g. `ECG`).
- Ensure file extension matches expected pattern (`.csv` by default).

## GSR sanity check failed

Symptoms:
- `Missing 'Timestamp' or 'GSR_CONDUCTANCE' in GSR dataframe.`
- `Raw GSR is entirely NaN / invalid.`
- `Raw GSR seems flatlined (very low variance).`

Fixes:
- Ensure time and conductance columns are numeric.
- Ensure conductance values are positive and not constant.
- Set `baseline_col` in config if the column name differs.

## Eye-tracking sanity check failed

Symptoms:
- `Missing timestamp column 'ts'`
- `No positive dt values (timestamps not increasing)`

Fixes:
- Ensure a time column exists and matches one of the accepted aliases.
- Ensure timestamps are numeric and increasing.
- Ensure at least 10 rows.

## ECG mode detection issues

Symptoms:
- `Unknown ECG input format...`
- `BPM input mode` and metrics skipped.

Fixes:
- Provide `RRI`/`RR`/`rr_ms` for RRI mode.
- For raw ECG, ensure columns are named `Timestamp` and `HR`.
- If your `HR` column is actually raw ECG (not BPM), verify values are not in the 40-200 BPM range.

## Head movement errors

Symptoms:
- `Missing required columns: [...]`

Fixes:
- Ensure all required head movement columns are present (see `input_data_schema.md`).
- Rename columns to match expected names.

## Empty metrics or summaries

Symptoms:
- `_summaries/<modality>/features_by_task.csv` missing.
- `No <MODALITY> metrics were produced for this run.`

Fixes:
- Ensure the modality list in `cfg["metrics"]` is not empty.
- Ensure the input files exist and pass sanity checks.
