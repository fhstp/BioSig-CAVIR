# Extending the Pipeline (New Modalities and Metrics)

Audience: developers extending the research prototype (new modalities, new metrics, new devices).

## What "extending" means in this project

The pipeline is orchestrated by `modules/pipeline.py` and delegates all modality-specific logic
to modality modules under `modules/<modality>/`.

In practice, extension falls into three categories:

- **New device / new column names**: add aliases or mapping rules so existing modality logic can run.
- **New metric within an existing modality**: implement the computation inside the modality module.
- **New modality**: create a new module and wire it into the orchestrator.

## Add support for a new device (existing modality)

Start with the device/column mapping layer:

- Eye tracking: extend `modules/eyetracking/unifier.py` (`CANON_ALIASES`).
- GSR: either rename the input column or configure `cfg["params"]["gsr"]["baseline_col"]`.
- ECG: rename columns to match expected names (`HR` for raw ECG; `RRI`/`RR`/`rr_ms` for RR mode).

See `docs/device_mapping.md` and `docs/input_data_schema.md`.

## Add a new metric (existing modality)

1. **Implement the metric** in the modality module, using the cleaned canonical representation:
   - ECG: add to `compute_requested_ecg_features` in `modules/ecg/ecg_pipeline.py`.
   - GSR: add to the metric dispatcher used in `modules/gsr/gsr_pipeline.py`.
   - Eye tracking: add to `compute_all_metrics` in `modules/eyetracking/metrics.py`.
2. **Expose it via config** by allowing the metric name in `cfg["metrics"][<modality>]`.
3. **Ensure reproducibility artifacts** are updated:
   - the metric appears in `features.csv`
   - any required params are captured in `<modality>/meta.json`

## Add a new modality (new module)

Minimum steps:

1. Create a new package `modules/<new_modality>/` and implement a runner function:

   - Convention used in this repo: `run_<new_modality>_pipeline(cfg, run_root, file_structure, data_root)`
   - The function should:
     - load input via `modules/io/load_modality.py`
     - validate/sanity-check input
     - produce a cleaned table (CSV), a `features.csv`, and a `meta.json`
     - optionally produce diagnostic plots (PNG)
     - return a `summary_df` with at least `participant` and `task` columns

2. Wire it into `modules/pipeline.py`:

   - add the modality name to `ALLOWED_MODALITIES`
   - import and call your runner
   - call `update_global_summary(run_root, "<MODALITY_NAME>", summary_df)`

3. Update documentation:

   - `docs/input_data_schema.md`: required columns and minimal example
   - `docs/output_schema.md`: outputs written by the modality
   - `docs/config_reference.md`: new modality params and metric names

## Output contract (what your modality should write)

The thesis and the existing modalities follow a consistent pattern per participant and task:

- `*_clean.csv` (or equivalent cleaned canonical table)
- `features.csv` (one row per participant-task with computed metrics)
- `meta.json` (params snapshot + QC/provenance + summary stats)
- optional `*.png` plots for diagnostics

