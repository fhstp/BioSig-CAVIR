# BioSig-CAVIR

Processing code for the **CAVIR dataset**, a multimodal biosignal dataset recorded while participants
worked through tasks in virtual reality. The dataset includes eye tracking from the VR headset, heart rate
(Polar RR intervals), EEG (Emotiv EPOC FLEX2) and self-reported mental effort ratings on the Paas
scale (PAAS).

This repository contains the code that produces the released data levels from the raw recordings:

```
01_RAW ──► preparser/ ─────────► 02_PREPARSED ──► multimodal_pipeline/ ──► 03_PREPROCESSED
  │        cut into task segments,                 eye tracking, heart rate,    cleaned signals,
  │        align all devices to Unix time          PAAS, quality control        features, QC tables
  │
  └──────► EEG_pipeline/ ────────────────────────────────────────────────────► 03_PREPROCESSED
           bad channels/segments, ICA + ICLabel, band-power features           EEG (.fif + features)
```

The methods are described in the CAVIR Data Descriptor (Methods, *Processing and dataset curation*
and *Feature extraction*).

## Repository structure

| Folder | Language | Input → output | Documentation |
| --- | --- | --- | --- |
| [`preparser/`](preparser/) | C# (.NET 8) | `01_RAW` → `02_PREPARSED` | [preparser/README.md](preparser/README.md), [full reference](preparser/docs/DataPreParser_Current_Documentation.md) |
| [`multimodal_pipeline/`](multimodal_pipeline/) | Python 3.13 | `02_PREPARSED` → `03_PREPROCESSED` (eye tracking, heart rate, PAAS) | [multimodal_pipeline/README.md](multimodal_pipeline/README.md), [`docs/`](multimodal_pipeline/docs/) |
| [`EEG_pipeline/`](EEG_pipeline/) | Python | `01_RAW` → `03_PREPROCESSED` (EEG) | [EEG pipeline](#eeg-pipeline) below |

The EEG pipeline reads the raw EmotivPRO exports directly. The preparser can also write EEG and
GSR segments, but these are not used and are not part of the released `02_PREPARSED` level.

## Data

Download the CAVIR dataset. The dataset folder contains `01_RAW`, `02_PREPARSED`, `03_PREPROCESSED`
and `participants.csv`. Data were collected in two periods, `2025_USTP` and `2026_USTP`, and each
level has one subfolder per period.

You don't need to run the preparser to reproduce `03_PREPROCESSED`, because `02_PREPARSED` is part of
the released dataset.

## Quick start

> The multimodal and EEG pipelines pin incompatible versions of NumPy and pandas, so install each
> one in its own virtual environment.

### 1. Preparser (optional)

Requires the [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0).

```bash
cd preparser
dotnet build DataPreParser/DataPreParser.csproj -c Release
dotnet build CavirTimeOffset/CavirTimeOffset.csproj -c Release
```

Copy the configuration of one period (`config/2025_USTP/` or `config/2026_USTP/`) into
`config/main/`, and the time-offset hook into `hooks/TimeOffsetHook/`, next to the executable. Then
parse all participants of that period:

```bash
DataPreParser parse --input-batch <dataset>/01_RAW/2026_USTP
```

See [preparser/README.md](preparser/README.md) for the runtime folder layout, single-participant
runs, configuration, and how the released files were reproduced byte for byte.

### 2. Multimodal pipeline (eye tracking, heart rate, PAAS)

```bash
cd multimodal_pipeline
python3.13 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
jupyter notebook pipeline.ipynb
```

Set `DATASET` in the first cell to the dataset folder and run all cells. The notebook uses the
parameters of the published run, and writes its output to `results/<timestamp>_nature_scientific/`.
See [multimodal_pipeline/README.md](multimodal_pipeline/README.md) for the processing steps,
quality-control thresholds and output layout.

### 3. EEG pipeline

```bash
cd EEG_pipeline
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Clean the raw recordings and split them into one .fif per task phase
python eeg_preprocessing.py --data-path <dataset>/01_RAW --output-dir <out>/03_PREPROCESSED

# Compute band-power features next to each phase file
python feature_extraction.py --input-dir <out>/03_PREPROCESSED --raw-dir <dataset>/01_RAW

# Optional: summarise the preprocessing log (needs: pip install matplotlib seaborn)
python log_analysis.py
```

## EEG pipeline

`EEG_pipeline/` processes the 14-channel Emotiv EPOC FLEX2 recordings, which were exported from
EmotivPRO as `*FLEX2*.csv`. It has three scripts.

### `eeg_preprocessing.py`: cleaning

The script searches `--data-path` recursively for FLEX2 recordings and processes them in parallel.
Each recording goes through these steps:

1. **Read.** Load the EEG channels, convert µV to V and remove the DC offset. Samples that EmotivPRO
   interpolated after Bluetooth packet loss, and gaps in the timestamps, are annotated as
   `BAD_packet_loss`. The CAVIR task phases (`scene<N>_intro|read|work|end`, baseline, calibration)
   come from the `*_markers_cavir.csv` file in the same folder.
2. **Filter.** Apply a 1–100 Hz band-pass and a 50 Hz notch filter that also removes the harmonics.
3. **Detect bad channels.** Use the PyPREP `NoisyChannels` criteria (NaN/flat, deviation,
   high-frequency noise, correlation with `frac_bad = 0.10`, no RANSAC), plus a variance check that
   flags channels with more than 5× the median variance.
4. **Reject or interpolate.** Reject the recording if more than 25 % of channels are bad, otherwise
   interpolate the bad channels. Then re-reference to the average.
5. **Mark bad segments.** Annotate 1 s windows with a peak-to-peak amplitude above 500 µV as
   `BAD_amplitude`. Reject the recording if less than 60 s of clean data remains.
6. **Remove artifacts with ICA.** Fit Picard ICA (99 % variance) on the clean data, then use ICLabel
   to remove eye, heart, muscle, line-noise and channel-noise components.
7. **Save.** Write one `.fif` file per task phase. Phases shorter than 1 s are skipped.

The `BAD_*` annotations are kept in the output, so MNE skips those segments when epoching. Each
file's `info["description"]` holds JSON provenance: the interpolated channels, the number of ICA
components, the removed components and the percentage of the recording marked bad.

### `feature_extraction.py`: band power

The script computes features for every phase file:

- Only the 12 channels present in every recording are used; F7 and FC6 are excluded.
- The clean data are cut into 2 s epochs with 1 s overlap, skipping `BAD_*` segments. Phases with
  fewer than 5 clean epochs get NaN features.
- Power is estimated with a Welch PSD and reported as log10 band power (µV²) for theta (4–8 Hz),
  alpha (8–13 Hz) and beta (13–30 Hz). Values are given per channel and per region (frontal,
  temporal, parietal, occipital, all).
- The theta/alpha ratio is frontal theta power divided by parietal-occipital alpha power.
- The scene's PAAS rating is read from the `*_paas.txt` files in `01_RAW`.

### Output

```
03_PREPROCESSED/<period>/<participant_id>/
├── CAVIR_Baseline/eeg/
│   └── <recording>_<phase>_raw.fif                 everything before scene 1 (resting
│                                                   baseline, eye calibration, ...)
└── CAVIR_Start<N>/eeg/
    ├── <recording>_scene<N>_<phase>_raw.fif        cleaned EEG of one task phase
    └── <recording>_scene<N>_<phase>_features.csv   one row: phase info, PAAS rating,
                                                    band power per region and channel
```

Processing results are logged to `EEG_pipeline/logs/preprocessing.log`. The log records `SUCCESS`,
`FAIL` (with the reason) or `CRASH` for each recording. `log_analysis.py` turns the log into a
summary, a `failed_files.csv` and a `preprocessing_report.png`.

### Options

| Option | Environment variable | Default |
| --- | --- | --- |
| `--data-path` | `EEG_DATA_PATH` | `<repo>/01_RAW/01_RAW` |
| `--output-dir` | `EEG_OUTPUT_DIR` | `<repo>/03_PREPROCESSED` |
| `--log-dir` | `EEG_LOG_DIR` | `EEG_pipeline/logs` |
| `--jobs`, `-j` | `EEG_N_JOBS` | Limited by CPU cores and RAM (about 2 GB per job, at most 64 jobs) |
| `--subjects` | | All participants |
| `--input-dir` (features) | `EEG_PREPROCESSED_DIR` | `<repo>/03_PREPROCESSED` |
| `--raw-dir` (features) | `EEG_DATA_PATH` | `<repo>/01_RAW` |

`--data-path` must point to the folder that contains the period folders (`2025_USTP/`,
`2026_USTP/`). The output path is built from the first two folder levels below it
(`<period>/<participant_id>`).

ICLabel needs a neural-network backend. `requirements.txt` installs PyTorch. For a smaller install,
use CPU-only PyTorch (`pip install torch --index-url https://download.pytorch.org/whl/cpu`) or
`onnxruntime` instead.

## Tests

The multimodal pipeline has a pytest suite:

```bash
cd multimodal_pipeline
pip install -r requirements-dev.txt
pytest
```

## License

[Apache License 2.0](LICENSE)

## Citation

If you use this code or the CAVIR dataset, please cite the CAVIR Data Descriptor:

> _TODO: add the Data Descriptor reference and the dataset DOI._
