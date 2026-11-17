"""Feature extraction for the preprocessed CAVIR phase files.

Input:  03_PREPROCESSED/<year>/<participant>/CAVIR_Start<N>|CAVIR_Baseline/eeg/<recording>_<phase>_raw.fif
        (written by script.py) and the Paas files (*_paas.txt, 2026) in 01_RAW.
Output: <recording>_<phase>_features.csv next to each phase .fif (one row: phase info, Paas
        rating of the scene, band power per region and per channel, theta/alpha ratio)

Method (constants below):
  - only the 12 channels present in every recording (no F7 / FC6)
  - 2 s epochs with 1 s overlap inside clean data (BAD_* segments skipped);
    phases with fewer than MIN_EPOCHS clean epochs get NaN features
  - Welch PSD (one Hann window per epoch, 0.5 Hz resolution), averaged over epochs
  - band power (log10 uV^2): theta 4-8, alpha 8-13, beta 13-30 Hz (delta/gamma left out:
    dominated by movement / eye / muscle artifacts in these VR recordings)
  - theta/alpha ratio: frontal theta power / parietal-occipital alpha power
"""
import argparse
import glob
import json
import logging
import os
import re
import warnings

import mne
import numpy as np
import pandas as pd
from joblib import Parallel, delayed

# ==========================================
# CONFIGURATION
# ==========================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
INPUT_DIR = os.environ.get("EEG_PREPROCESSED_DIR", os.path.join(PROJECT_DIR, "03_PREPROCESSED"))
RAW_DIR = os.environ.get("EEG_DATA_PATH", os.path.join(PROJECT_DIR, "01_RAW"))

# Channels recorded in every recording (18 recordings have no F7, one has no FC6).
CHANNELS = ["AF3", "F3", "FC5", "T7", "P7", "O1", "O2", "P8", "T8", "F4", "F8", "AF4"]
REGIONS = {
    "all": CHANNELS,
    "frontal": ["AF3", "AF4", "F3", "F4"],
    "temporal": ["T7", "T8"],
    "parietal": ["P7", "P8"],
    "occipital": ["O1", "O2"],
}
POSTERIOR = ["P7", "P8", "O1", "O2"]
BANDS = {"theta": (4.0, 8.0), "alpha": (8.0, 13.0), "beta": (13.0, 30.0)}

EPOCH_S = 2.0
EPOCH_OVERLAP_S = 1.0
MIN_EPOCHS = 5
PSD_FMIN, PSD_FMAX = 1.0, 45.0

SCENE_FOLDER_RE = re.compile(r"^CAVIR_Start(\d+)$")

# Per-channel feature columns (also aggregated per region in features_phase.csv).
CHANNEL_FEATURES = [f"{b}_logpow" for b in BANDS]


# ==========================================
# PER-FILE FEATURES
# ==========================================
def _phase_label(raw):
    """The phase annotation (the longest non-BAD annotation) of a phase file."""
    phases = [(d, desc) for d, desc in zip(raw.annotations.duration, raw.annotations.description)
              if not desc.startswith("BAD")]
    return max(phases)[1] if phases else None


def _clean_epochs(raw):
    if raw.times[-1] < EPOCH_S:
        return None
    try:
        epochs = mne.make_fixed_length_epochs(raw, duration=EPOCH_S, overlap=EPOCH_OVERLAP_S,
                                              reject_by_annotation=True, preload=True, verbose=False)
    except (ValueError, RuntimeError):
        return None
    return epochs if len(epochs) else None


def channel_features(epochs):
    """DataFrame (index = channel) with log10 band power (uV^2) per band."""
    psd = epochs.compute_psd(method="welch", fmin=PSD_FMIN, fmax=PSD_FMAX,
                             n_fft=int(EPOCH_S * epochs.info["sfreq"]), verbose=False)
    p, freqs = psd.get_data(return_freqs=True)
    p = p.mean(axis=0) * 1e12                        # V^2/Hz -> uV^2/Hz, averaged over epochs
    df_hz = freqs[1] - freqs[0]
    power = {f"{b}_logpow": np.log10(p[:, (freqs >= lo) & (freqs < hi)].sum(axis=1) * df_hz)
             for b, (lo, hi) in BANDS.items()}
    return pd.DataFrame(power, index=epochs.ch_names)[CHANNEL_FEATURES]


def phase_features(ch):
    """Band power per region and the theta/alpha ratio from the per-channel table."""
    lin = 10 ** ch                                   # back to uV^2: average power, then log
    out = {f"{region}_{f}": np.log10(lin.loc[chans, f].mean())
           for region, chans in REGIONS.items() for f in CHANNEL_FEATURES}
    out["theta_alpha_ratio"] = (lin.loc[REGIONS["frontal"], "theta_logpow"].mean()
                                / lin.loc[POSTERIOR, "alpha_logpow"].mean())
    return out


def process_file(path, input_dir):
    """(phase row dict, per-channel DataFrame or None) for one phase file."""
    mne.set_log_level("ERROR")
    warnings.filterwarnings("ignore")
    cohort, participant, folder = os.path.relpath(path, input_dir).split(os.sep)[:3]
    raw = mne.io.read_raw_fif(path, preload=True)
    meta = json.loads(raw.info.get("description") or "{}")
    interpolated = meta.get("interpolated_channels", [])
    phase = _phase_label(raw)
    scene = SCENE_FOLDER_RE.match(folder)

    row = dict(cohort=cohort, participant=participant, folder=folder,
               scene=int(scene.group(1)) if scene else np.nan, phase=phase,
               subphase=phase.split("_", 1)[1] if scene and phase else phase,
               duration_s=round(raw.times[-1] + 1 / raw.info["sfreq"], 2),
               clean_s=round(raw.get_data(picks=[0], reject_by_annotation="omit").shape[1]
                             / raw.info["sfreq"], 2),
               n_epochs=0, interpolated=",".join(interpolated),
               recording_bad_pct=meta.get("recording_bad_pct", np.nan),
               ica_removed=len(meta.get("ica_removed", [])), file=os.path.relpath(path, input_dir))

    missing = [c for c in CHANNELS if c not in raw.ch_names]
    if missing:
        row["error"] = f"missing channels {missing}"
        return row, None
    epochs = _clean_epochs(raw.pick(CHANNELS))
    row["n_epochs"] = 0 if epochs is None else len(epochs)
    if row["n_epochs"] < MIN_EPOCHS:
        return row, None

    ch = channel_features(epochs)
    row.update(phase_features(ch))
    ch.insert(0, "file", row["file"])
    return row, ch.rename_axis("channel").reset_index()


# ==========================================
# PAAS RATINGS
# ==========================================
def read_paas(path):
    """({scene: first rating}, repeated scenes) from a <...>_paas.txt (lines 'scene<N>_end;<rating>').
    If a scene was rated twice, the first rating is used (it matches the scene's work phase
    in the marker stream)."""
    ratings, repeated = {}, []
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            m = re.match(r"^scene(\d+)_end;([\d.]+)", line.strip())
            if m:
                scene = int(m.group(1))
                if scene in ratings:
                    repeated.append(scene)
                else:
                    ratings[scene] = float(m.group(2))
    return ratings, repeated


def paas_table(raw_dir):
    """DataFrame (participant, scene, paas, paas_repeated) for every participant folder in raw_dir."""
    paas = []
    for part_dir in sorted(glob.glob(os.path.join(raw_dir, "*", "*"))):
        if not os.path.isdir(part_dir):
            continue
        participant = os.path.basename(part_dir)
        files = glob.glob(os.path.join(part_dir, "**", "*_paas.txt"), recursive=True)
        for f in sorted(files)[:1]:
            ratings, repeated = read_paas(f)
            paas += [dict(participant=participant, scene=s, paas=r, paas_repeated=s in repeated)
                     for s, r in ratings.items()]
    return pd.DataFrame(paas, columns=["participant", "scene", "paas", "paas_repeated"])


# ==========================================
# MAIN
# ==========================================
def write_phase_files(phases, channels, input_dir):
    """<recording>_<phase>_features.csv next to each phase .fif: one row with the phase
    columns plus per-channel band power (<channel>_<band>_logpow). Phases with too little
    clean data get a file too (features NaN, see n_epochs)."""
    wide = channels.set_index(["file", "channel"])[CHANNEL_FEATURES].unstack("channel")
    wide.columns = [f"{c}_{f}" for f, c in wide.columns]
    cols = list(phases.columns) + [f"{c}_{f}" for c in CHANNELS for f in CHANNEL_FEATURES]
    table = phases.join(wide, on="file").reindex(columns=cols)
    for i in range(len(table)):
        row = table.iloc[[i]]
        row.to_csv(os.path.join(input_dir, row.file.iat[0].replace("_raw.fif", "_features.csv")),
                   index=False)
    return len(table)


def parse_args():
    parser = argparse.ArgumentParser(description="Feature extraction for preprocessed CAVIR phase files.")
    parser.add_argument("--input-dir", default=INPUT_DIR,
                        help="Output of script.py (env: EEG_PREPROCESSED_DIR). Default: %(default)s")
    parser.add_argument("--raw-dir", default=RAW_DIR,
                        help="Raw data with the Paas files (env: EEG_DATA_PATH). Default: %(default)s")
    parser.add_argument("--jobs", "-j", type=int, default=-1, help="Parallel workers (default: all cores).")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    files = sorted(glob.glob(os.path.join(args.input_dir, "*", "*", "CAVIR_*", "eeg", "*_raw.fif")))
    logging.info(f"{len(files)} phase files in {args.input_dir}")
    if not files:
        raise SystemExit("No phase files found; run script.py first or set --input-dir.")

    results = Parallel(n_jobs=args.jobs)(delayed(process_file)(f, args.input_dir) for f in files)
    phases = pd.DataFrame([r for r, _ in results])
    channels = pd.concat([c for _, c in results if c is not None], ignore_index=True)

    phases = phases.merge(paas_table(args.raw_dir), on=["participant", "scene"], how="left")

    first = ["cohort", "participant", "folder", "scene", "phase", "subphase", "duration_s", "clean_s",
             "n_epochs", "paas", "paas_repeated"]
    phases = phases[first + [c for c in phases.columns if c not in first]]
    n_written = write_phase_files(phases, channels, args.input_dir)

    n_ok = phases["all_theta_logpow"].notna().sum()
    logging.info(f"{n_written} *_features.csv files written next to the phase files in {args.input_dir} "
                 f"({n_ok} with >= {MIN_EPOCHS} clean epochs, {phases.participant.nunique()} participants)")
