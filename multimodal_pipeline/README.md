# Multimodal processing pipeline

Python pipeline that processes the eye-tracking, heart-rate and PAAS data of the CAVIR dataset. It
produces the `03_PREPROCESSED` level from `02_PREPARSED`: cleaned signals, features and
quality-control measures per participant and task segment.

The methods are described in the Data Descriptor (Methods, *Processing and dataset curation* and
*Feature extraction*). EEG was processed with a separate pipeline (`../eeg/`).

## Requirements

Python 3.13 and the packages in `requirements.txt` (the versions used for the published run):

```
python -m venv .venv
.venv\Scripts\activate          # Windows; on Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
```

## Reproducing the dataset

1. Download the CAVIR dataset.
2. Open `pipeline.ipynb` from this folder (`jupyter notebook pipeline.ipynb`).
3. Set `DATASET` in the first cell to the dataset folder.
4. Run all cells.

The notebook reads the participant list from `participants.csv`, copies the preparsed files of
both data-collection periods into `data/` (the pipeline expects one folder per participant) and
runs the pipeline with the parameters of the published run (`03_PREPROCESSED/run_metadata.json`).
The output is written to `results/<timestamp>_nature_scientific/`.

Rerunning the notebook on the published preparsed data reproduces the published cleaned signals,
features and QC tables. In the released dataset, the participant folders were additionally sorted
into one folder per data-collection period (`03_PREPROCESSED/<cohort>/<participant_id>/`).

## Output

```
results/<timestamp>_nature_scientific/
├── run_metadata.json                  configuration of the run
├── <participant_id>/CAVIR_StartN/
│   ├── eye_tracking/
│   │   ├── eyetracking_clean.csv      samples on a 60 Hz grid with validity masks, velocity,
│   │   │                              fixation/saccade/blink labels
│   │   ├── features.csv
│   │   ├── meta.json                  parameters and quality measures of the segment
│   │   └── *.png                      quick-look plots
│   └── ecg/                           heart rate (Polar RR intervals)
│       ├── ecg_clean.csv              RR intervals with validity flag and exclusion reason
│       ├── features.csv               RMSSD, SDNN, pNN50 (own and NeuroKit2 implementation)
│       ├── meta.json
│       └── rr_timeseries.png
└── _summaries/
    ├── summary_all_modalities.csv
    ├── <modality>/features_by_task.csv
    └── qc/                            QC per segment, per cohort and per modality combination,
                                       thresholds and report
```

Heart-rate files and folders are named `ecg` for historical reasons; they contain RR intervals, not
an ECG waveform.

## Processing steps

**Eye tracking** (`modules/eyetracking/`)

1. Harmonise column names and units, and check the sampling rate and timestamps.
2. Remove repeated rows (the headset writes one row per rendered frame, but new samples arrive at
   60 Hz) and place the samples on a regular 60 Hz grid (`resample.py`).
3. Detect blinks as bilateral signal loss of 50–500 ms (`blinks.py`).
4. Mark valid gaze and pupil samples (`validity_mask.py`); quality measure: track loss excluding
   blinks.
5. Compute angular gaze velocity and classify fixations and saccades with a three-state I-VT with
   hysteresis (`segmentation.py`).
6. Compute fixation, saccade, blink and pupil features (`metrics.py`).

**Heart rate** (`modules/ecg/`)

1. Convert RR intervals from 1/1024 s to ms and reconstruct beat times from their cumulative sum.
2. Mark intervals outside 40–200 bpm and missed beats as invalid, and detect artifact beats with the
   Kubios algorithm (Lipponen & Tarvainen, 2019) as implemented in NeuroKit2 (`rr_cleaning.py`).
   Flagged beats are excluded, not interpolated.
3. Discard the first 5 s of each segment.
4. Compute RMSSD, SDNN and pNN50 from valid beats; successive differences use adjacent valid beats
   only (`ecg_metrics/`).

**PAAS** (`modules/paas/`): reads the ratings from `paas.csv` per task.

**Quality control** (`modules/qc/`): applies the thresholds per segment and modality and writes the
QC tables. Eye tracking: track loss ≤ 25 %. Heart rate: ≤ 5 % artifact beats, ≥ 30 s of clean RR
data and ≥ 80 % coverage of the task.

The modules for raw ECG (R-peak detection), GSR, EEG and head movement belong to the general
pipeline and are not used for the CAVIR dataset.

## Repository structure

```
modules/
├── pipeline.py        entry point: run_pipeline(cfg)
├── eyetracking/       eye-tracking processing and features
├── ecg/               heart-rate (RR interval) processing and HRV features
├── paas/              PAAS ratings
├── qc/                quality control
├── io/                loading, saving, folder structure, summaries
├── viz/               quick-look plots
└── eeg/, gsr/, head_movement/   not used for CAVIR
docs/                  configuration reference, input and output schema, metric definitions
tests/                 unit tests
pipeline.ipynb         reproduces the CAVIR run
```

## Tests

```
pip install -r requirements-dev.txt
pytest
```
