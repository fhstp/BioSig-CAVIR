import argparse
import json
import re
import mne
import sys
import os
import numpy as np
import pandas as pd
import logging
from datetime import datetime, timezone
from joblib import Parallel, delayed
from pyprep.find_noisy_channels import NoisyChannels
from mne.preprocessing import ICA
from mne_icalabel import label_components

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)

MAX_CONCURRENT_JOBS = 64
EST_GB_PER_JOB = 2

BASE_PATH = os.environ.get("EEG_DATA_PATH", os.path.join(PROJECT_DIR, "01_RAW", "01_RAW"))
OUTPUT_DIR = os.environ.get("EEG_OUTPUT_DIR", os.path.join(PROJECT_DIR, "03_PREPROCESSED"))

# Emotiv EPOC FLEX2 exports from EmotivPRO, e.g. <id>_FLEX2_<...>.md.bp.csv / .md.pm.bp.csv
EEG_FILE_TAG = "FLEX2"

# CAVIR task phases come from the VR marker stream next to the EEG file
# (<...>_markers_cavir.csv: UNIX time; time since start; phase label; tracking data ...).
# Each preprocessed recording is saved as one .fif per phase:
#   <output>/<year>/<participant>/CAVIR_Start<N>/eeg/<recording>_scene<N>_<intro|read|work|end>_raw.fif
#   <output>/<year>/<participant>/CAVIR_Baseline/eeg/<recording>_<phase>_raw.fif   (everything before scene 1)
CAVIR_MARKER_SUFFIX = "markers_cavir.csv"
SCENE_PHASE_RE = re.compile(r"^scene(\d+)_[A-Za-z]+$")
SCENE_FOLDER = "CAVIR_Start{}"
BASELINE_FOLDER = "CAVIR_Baseline"
EEG_SUBFOLDER = "eeg"                    # inside each CAVIR_* folder
MIN_PHASE_S = 1.0                        # phases shorter than this (e.g. cut off by the EEG end) are not saved
MONTAGE_NAME = "colin27_1020"    # FLEX2 electrodes use 10-20 names (formerly "standard_1020" in MNE)
LINE_FREQ = 50.0                 # mains frequency in Austria/Europe

BAD_CHANNEL_THRESHOLD_PERCENT = 0.25     # reject recording if more channels than this are bad
VARIANCE_SAFETY_NET_MULTIPLIER = 5.0     # extra bad channel if variance > 5x median variance
# PyPREP marks a channel bad-by-correlation if its max correlation with any other channel
# is < 0.4 in more than this fraction of 1 s windows. PREP's default (1%) is meant for
# dense lab caps; with 13-14 sparse electrodes and VR movement it flags nearly every channel.
CORRELATION_FRAC_BAD = 0.10

# Segments (1 s windows) where any channel exceeds this peak-to-peak amplitude are
# annotated as BAD_amplitude. They stay in the data but are skipped when fitting ICA
# (and by MNE epoching later). Eye blinks (~100-200 uV) stay below it so ICA can learn them.
ARTIFACT_PTP_UV = 500.0
ARTIFACT_WINDOW_S = 1.0
MIN_CLEAN_DATA_S = 60.0                  # reject recording if less clean data is left for ICA

# Global Log Path (Must be defined at top level)
LOG_DIR = os.environ.get("EEG_LOG_DIR", os.path.join(SCRIPT_DIR, "logs"))
LOG_FILE = 'preprocessing.log'

# ==========================================
# LOGGING SETUP FUNCTION
# ==========================================
def configure_logger(log_dir=LOG_DIR):
    """
    Configures logging for the current process (Main or Worker).
    This ensures every parallel job writes to the file.
    """
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.join(log_dir, LOG_FILE)

    root_logger = logging.getLogger()

    # Avoid adding duplicate handlers if joblib re-uses a process
    if not root_logger.handlers:
        root_logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - [PID %(process)d] - %(levelname)s - %(message)s')

        # 1. File Handler (The fix for empty logs)
        # mode='a' is atomic on POSIX (Linux), so parallel writes generally work fine.
        file_handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

        # 2. Console Handler (So you see progress in the terminal)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

# ==========================================
# FLEX2 (EmotivPRO CSV) READER
# ==========================================
def is_flex2_eeg_file(filename):
    """The EEG data file of a FLEX2 export (not its _intervalMarker.csv / .json companions)."""
    return (EEG_FILE_TAG in filename and filename.endswith(".csv")
            and not filename.endswith("_intervalMarker.csv"))


def recording_stem(filename):
    """'<name>.md.pm.bp.csv' -> '<name>'"""
    return re.sub(r"(\.(md|pm|bp))*\.csv$", "", filename)


def _marker_onsets(timestamps, abs_times):
    """Map absolute UNIX times to sample indices.

    Bluetooth packet loss means the sample count drifts from wall-clock time,
    so markers are placed at the sample whose timestamp is closest.
    """
    idx = np.clip(np.searchsorted(timestamps, abs_times), 0, len(timestamps) - 1)
    return idx


def read_interval_markers(csv_path, timestamps, sfreq):
    """Interval markers (e.g. Eyes Opened / Eyes Closed) as mne.Annotations.

    Uses <stem>_intervalMarker.csv if present, else the 'Markers' list in <stem>.json.
    """
    stem = os.path.join(os.path.dirname(csv_path), recording_stem(os.path.basename(csv_path)))
    starts, durations, labels = [], [], []

    marker_csv = stem + "_intervalMarker.csv"
    marker_json = stem + ".json"
    if os.path.isfile(marker_csv) and os.path.getsize(marker_csv) > 0:
        markers = pd.read_csv(marker_csv)
        starts = markers["timestamp"].astype(float).tolist()
        durations = markers["duration"].astype(float).tolist()
        labels = markers["type"].astype(str).tolist()
    elif os.path.isfile(marker_json):
        with open(marker_json, encoding="utf-8") as fh:
            for m in json.load(fh).get("Markers", []):
                if m.get("deleted"):
                    continue
                start = datetime.fromisoformat(m["startDatetime"]).timestamp()
                end = datetime.fromisoformat(m.get("endDatetime", m["startDatetime"])).timestamp()
                starts.append(start)
                durations.append(end - start)
                labels.append(str(m.get("label", m.get("value", "marker"))).replace(" ", "_"))

    if not starts:
        return None
    onsets = _marker_onsets(timestamps, np.asarray(starts)) / sfreq
    return mne.Annotations(onsets, durations, labels)


def _read_marker_stream(path):
    """(timestamp, phase) rows of a CAVIR marker stream; drops truncated/unlabelled rows."""
    m = pd.read_csv(path, sep=";", header=None, usecols=[0, 2], names=["ts", "phase"],
                    dtype={"phase": str}, on_bad_lines="skip")
    m["ts"] = pd.to_numeric(m["ts"], errors="coerce")
    return m.dropna().sort_values("ts", kind="stable").reset_index(drop=True)


def read_cavir_phases(csv_path, timestamps, sfreq):
    """CAVIR task phases (scene1_intro, scene1_work, ..., eeg_eyes_open_active, ...) as
    mne.Annotations, taken from the *markers_cavir.csv in the EEG file's folder.

    Every run of consecutive rows with the same label becomes one annotation from its first
    to its last timestamp, clipped to the EEG recording. Returns (annotations or None, notes).
    """
    folder = os.path.dirname(csv_path)
    candidates = [os.path.join(folder, f) for f in os.listdir(folder) if f.endswith(CAVIR_MARKER_SUFFIX)]
    if not candidates:
        return None, f"no *{CAVIR_MARKER_SUFFIX} in folder"

    # If there are several marker files, use the one that overlaps the EEG recording most.
    def overlap(m):
        return max(0.0, min(m.ts.max(), timestamps[-1]) - max(m.ts.min(), timestamps[0])) if len(m) else 0.0
    streams = [_read_marker_stream(p) for p in candidates]
    m = max(streams, key=overlap)
    if overlap(m) <= 0:
        return None, "marker stream does not overlap the EEG recording"

    run_id = (m["phase"] != m["phase"].shift()).cumsum()
    runs = m.groupby(run_id).agg(phase=("phase", "first"), start=("ts", "min"), end=("ts", "max"))

    onsets, durations, labels, notes = [], [], [], []
    for r in runs.itertuples():
        start, end = max(r.start, timestamps[0]), min(r.end, timestamps[-1])
        if end <= start:
            notes.append(f"{r.phase} outside EEG")
            continue
        if start > r.start or end < r.end:
            notes.append(f"{r.phase} clipped to {end - start:.0f}/{r.end - r.start:.0f}s")
        i0, i1 = _marker_onsets(timestamps, np.array([start, end]))
        onsets.append(i0 / sfreq)
        durations.append((i1 - i0) / sfreq)
        labels.append(r.phase)
    if not labels:
        return None, "; ".join(notes)
    return mne.Annotations(onsets, durations, labels), "; ".join(notes)


def phase_folder(description, first_scene_onset, onset):
    """Output sub-folder for a phase annotation, or None if it is not exported."""
    scene = SCENE_PHASE_RE.match(description)
    if scene:
        return SCENE_FOLDER.format(int(scene.group(1)))
    if description.startswith("BAD") or description.startswith("wait_for"):
        return None
    if onset < first_scene_onset:          # resting baseline, eye calibration, starting_phase, ...
        return BASELINE_FOLDER
    return None


def save_phases(raw, participant_dir, stem):
    """Save every CAVIR phase of `raw` as its own .fif. Returns the number of files written.

    BAD_* annotations inside a phase are kept, so MNE still skips them when epoching.
    """
    ann = raw.annotations
    scene_onsets = [o for o, d in zip(ann.onset, ann.description) if SCENE_PHASE_RE.match(d)]
    first_scene = min(scene_onsets) if scene_onsets else np.inf
    t_last = raw.times[-1]
    written = {}
    for onset, duration, desc in zip(ann.onset, ann.duration, ann.description):
        folder = phase_folder(desc, first_scene, onset)
        if folder is None:
            continue
        tmin = onset - raw.first_time
        tmax = min(tmin + duration, t_last)
        if tmax - tmin < MIN_PHASE_S:
            continue
        name = re.sub(r"[^\w.-]", "_", desc)
        written[name] = written.get(name, 0) + 1
        if written[name] > 1:                 # same label twice in one recording
            name = f"{name}_{written[name]}"
        out_dir = os.path.join(participant_dir, folder, EEG_SUBFOLDER)
        os.makedirs(out_dir, exist_ok=True)
        raw.copy().crop(tmin, tmax, include_tmax=False).save(
            os.path.join(out_dir, f"{stem}_{name}_raw.fif"), overwrite=True)
    return sum(written.values())


def _runs(mask):
    """(start, stop) index pairs of consecutive True values."""
    edges = np.diff(np.concatenate([[0], mask.astype(np.int8), [0]]))
    return zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1))


def packet_loss_annotations(timestamps, interpolated, sfreq):
    """BAD_packet_loss annotations for samples EmotivPRO filled in after Bluetooth
    packet loss (EEG.Interpolated) and for gaps where samples are missing entirely."""
    onsets, durations = [], []
    for start, stop in _runs(interpolated):
        onsets.append(start / sfreq)
        durations.append((stop - start) / sfreq)
    for i in np.flatnonzero(np.diff(timestamps) > 1.5 / sfreq):
        onsets.append(max(0.0, (i + 1) / sfreq - 0.25))   # mark +-0.25 s around the jump
        durations.append(0.5)
    return mne.Annotations(onsets, durations, ["BAD_packet_loss"] * len(onsets))


def read_flex2_csv(csv_path):
    """Read an EmotivPRO FLEX2 CSV export into an mne.io.Raw (EEG channels only, in volts)."""
    with open(csv_path, encoding="utf-8") as fh:
        meta_line = fh.readline()
    meta = dict(kv.split(":", 1) for kv in meta_line.strip().strip(",").split(", ") if ":" in kv)
    m = re.search(r"eeg_(\d+(?:\.\d+)?)", meta.get("sampling rate", ""))
    if not m:
        raise ValueError(f"No EEG sampling rate in header line: {meta_line[:200]!r}")
    sfreq = float(m.group(1))

    # Electrode columns are 'EEG.<10-20 name>'; other 'EEG.*' columns are device metadata.
    header = pd.read_csv(csv_path, skiprows=1, nrows=0).columns
    montage_names = set(mne.channels.make_standard_montage(MONTAGE_NAME).ch_names)
    ch_cols = [c for c in header if c.startswith("EEG.") and c[4:] in montage_names]
    if not ch_cols:
        raise ValueError("No EEG electrode columns found")
    extra_cols = [c for c in ("EEG.Interpolated",) if c in header]

    df = pd.read_csv(csv_path, skiprows=1, usecols=["Timestamp"] + ch_cols + extra_cols,
                     dtype=np.float64, engine="c")
    df = df.dropna(subset=ch_cols, how="all")
    df[ch_cols] = df[ch_cols].interpolate(limit_direction="both")
    timestamps = df["Timestamp"].to_numpy()

    data = df[ch_cols].to_numpy().T * 1e-6                 # µV -> V
    data -= np.median(data, axis=1, keepdims=True)         # remove the ~4200 µV DC offset

    info = mne.create_info([c[4:] for c in ch_cols], sfreq, "eeg")
    raw = mne.io.RawArray(data, info, verbose=False)
    raw.set_meas_date(datetime.fromtimestamp(timestamps[0], tz=timezone.utc))

    annotations = mne.Annotations([], [], [])
    markers = read_interval_markers(csv_path, timestamps, sfreq)
    if markers is not None:
        annotations += markers
    phases, phase_notes = read_cavir_phases(csv_path, timestamps, sfreq)
    if phases is not None:
        annotations += phases
    interpolated = df["EEG.Interpolated"].to_numpy() > 0 if extra_cols else np.zeros(len(df), bool)
    annotations += packet_loss_annotations(timestamps, interpolated, sfreq)
    raw.set_annotations(annotations)

    expected = int(round((timestamps[-1] - timestamps[0]) * sfreq)) + 1
    stats = {
        "channels": len(ch_cols),
        "duration_s": round(len(df) / sfreq, 1),
        "missing_samples": max(0, expected - len(df)),
        "interpolated_pct": round(100 * df["EEG.Interpolated"].mean(), 2) if extra_cols else None,
        "markers": 0 if markers is None else len(markers),
        "cavir_phases": 0 if phases is None else len(phases),
    }
    if phase_notes:
        stats["phase_notes"] = phase_notes
    return raw, stats

# ==========================================
# PREPROCESSING
# ==========================================
def _good_data_raw(raw):
    """Copy of `raw` with BAD_* annotated segments cut out."""
    data = raw.get_data(reject_by_annotation="omit")
    return mne.io.RawArray(data, raw.info.copy(), verbose=False)


def annotate_high_amplitude(raw):
    """BAD_amplitude annotations for windows with peak-to-peak > ARTIFACT_PTP_UV on any good channel."""
    picks = mne.pick_types(raw.info, eeg=True, exclude="bads")
    win = int(round(ARTIFACT_WINDOW_S * raw.info["sfreq"]))
    n_win = raw.n_times // win
    data = raw.get_data(picks=picks)[:, : n_win * win].reshape(len(picks), n_win, win)
    bad = (np.ptp(data, axis=2) > ARTIFACT_PTP_UV * 1e-6).any(axis=0)
    onsets, durations = [], []
    for start, stop in _runs(bad):
        onsets.append(raw.first_time + start * ARTIFACT_WINDOW_S)
        durations.append((stop - start) * ARTIFACT_WINDOW_S)
    raw.set_annotations(raw.annotations + mne.Annotations(
        onsets, durations, ["BAD_amplitude"] * len(onsets), orig_time=raw.annotations.orig_time))


def bad_fraction(raw):
    """Fraction of the recording covered by BAD_* annotations."""
    n_good = raw.get_data(picks=[0], reject_by_annotation="omit").shape[1]
    return 1 - n_good / raw.n_times


def preprocess_eeg_file(raw):
    """Low-density (13-14 channel) cleaning:

    1. 1-100 Hz band-pass (range expected by ICLabel) + 50 Hz notch
    2. bad channels: PyPREP NoisyChannels criteria (NaN/flat, deviation, HF noise,
       correlation with CORRELATION_FRAC_BAD; no RANSAC) on the original CMS/DRL-referenced
       data without packet-loss segments, plus a variance safety net
    3. reject if > BAD_CHANNEL_THRESHOLD_PERCENT channels are bad, else interpolate them
    4. average reference
    5. annotate high-amplitude segments as BAD_amplitude
    6. ICA (Picard) fitted on non-BAD data, ICLabel removes eye/heart/muscle/line/channel-noise ICs

    BAD_* annotations (packet loss, amplitude) are kept in the output for later epoching.
    """
    montage = mne.channels.make_standard_montage(MONTAGE_NAME)
    raw.set_montage(montage, match_case=False, on_missing='warn')

    nyquist = raw.info["sfreq"] / 2
    raw.filter(l_freq=1.0, h_freq=min(100.0, nyquist - 1), fir_design='firwin', verbose=False)
    raw.notch_filter(np.arange(LINE_FREQ, nyquist, LINE_FREQ), verbose=False)

    # --- bad channel detection (original reference, without packet-loss segments) ---
    # Average-referencing only 13-14 channels first would spread artifacts to all
    # channels and lower their correlations, so detection runs before re-referencing.
    detect = _good_data_raw(raw)
    try:
        noisy = NoisyChannels(detect, do_detrend=False, random_state=97)
        noisy.find_bad_by_nan_flat()
        noisy.find_bad_by_deviation()
        noisy.find_bad_by_hfnoise()
        noisy.find_bad_by_correlation(frac_bad=CORRELATION_FRAC_BAD)
        bads = list(noisy.get_bads())
    except Exception as e:
        return None, f"Bad-channel detection failed: {e}"

    picks = mne.pick_types(detect.info, eeg=True)
    remaining = [p for p in picks if detect.ch_names[p] not in bads]
    if remaining:
        ch_vars = np.var(detect.get_data(picks=remaining), axis=1)
        bads += [detect.ch_names[p] for p, v in zip(remaining, ch_vars)
                 if v > np.median(ch_vars) * VARIANCE_SAFETY_NET_MULTIPLIER]

    raw.info['bads'] = sorted(set(bads))
    bad_channels = list(raw.info['bads'])
    total_channels = len(picks)
    if total_channels > 0 and (len(bad_channels) / total_channels > BAD_CHANNEL_THRESHOLD_PERCENT):
        return None, f"Too many bad channels: {len(bad_channels)}/{total_channels} {bad_channels}"

    if bad_channels:
        raw.interpolate_bads(reset_bads=True, verbose=False)
    raw.set_eeg_reference('average', projection=False, verbose=False)

    # --- bad segments ---
    annotate_high_amplitude(raw)
    frac_bad = bad_fraction(raw)
    clean_s = (1 - frac_bad) * raw.n_times / raw.info["sfreq"]
    if clean_s < MIN_CLEAN_DATA_S:
        return None, f"Too little clean data: {clean_s:.0f}s ({100 * frac_bad:.0f}% marked BAD)"

    # --- ICA + ICLabel ---
    try:
        ica = ICA(n_components=0.99, method='picard', fit_params=dict(ortho=False, extended=True), random_state=97, max_iter='auto')
        ica.fit(raw, picks='eeg', reject_by_annotation=True)
        label_components(raw, ica, method='iclabel')
        exclude_idx = [idx for label in ["eog", "ecg", "muscle", "line_noise", "ch_noise"]
                       if label in ica.labels_ for idx in ica.labels_[label]]
        ica.exclude = sorted(list(set(exclude_idx)))
        cleaned_raw = raw.copy()
        ica.apply(cleaned_raw)
    except Exception as e:
        return None, f"ICA Failed: {e}"

    cleaned_raw.pick('eeg')
    # Provenance for later analyses (e.g. skip asymmetry features on interpolated channels).
    cleaned_raw.info["description"] = json.dumps({
        "interpolated_channels": bad_channels,
        "ica_components": int(ica.n_components_),
        "ica_removed": [int(i) for i in ica.exclude],
        "recording_bad_pct": round(100 * frac_bad, 2),
    })
    return cleaned_raw, (f"interpolated={bad_channels}, BAD time={100 * frac_bad:.1f}%, "
                         f"ICA removed {len(ica.exclude)}/{ica.n_components_} components")


# ==========================================
# WORKER FUNCTION (Run by each core)
# ==========================================
def process_file(csv_path, base_path, output_dir, log_dir):
    # CRITICAL: Re-initialize logger inside the worker process
    configure_logger(log_dir)
    mne.set_log_level('WARNING')
    logging.getLogger('pyprep').setLevel(logging.ERROR)  # hides repeated 'ransac' notices

    rel_path = os.path.relpath(csv_path, base_path)
    try:
        logging.info(f"Processing {rel_path}")
        raw, stats = read_flex2_csv(csv_path)
        logging.info(f"Loaded {rel_path}: " + ", ".join(f"{k}={v}" for k, v in stats.items()))
        if not stats["cavir_phases"]:
            # Output is one file per CAVIR phase, so there is nothing to save without markers.
            logging.error(f"FAIL: {rel_path} -> No CAVIR phase markers: {stats.get('phase_notes', '')}")
            return

        cleaned_raw, status_msg = preprocess_eeg_file(raw)

        if cleaned_raw is not None:
            # <output>/<year>/<participant>/CAVIR_Start<N>/... (input sub-folders below the participant are dropped)
            parts = rel_path.split(os.sep)
            participant_dir = os.path.join(output_dir, *parts[:2]) if len(parts) >= 3 \
                else os.path.join(output_dir, os.path.dirname(rel_path))
            n_files = save_phases(cleaned_raw, participant_dir, recording_stem(os.path.basename(csv_path)))
            if n_files == 0:
                logging.error(f"FAIL: {rel_path} -> No CAVIR phase could be saved")
            else:
                logging.info(f"SUCCESS: {rel_path} -> {participant_dir} [{status_msg}, {n_files} phase files]")
        else:
            logging.error(f"FAIL: {rel_path} -> {status_msg}")

    except Exception as e:
        logging.error(f"CRASH: {rel_path} -> {e}")


def find_eeg_files(base_path, subjects=None):
    """All FLEX2 EEG CSVs below base_path (optionally only paths containing one of `subjects`)."""
    files = []
    for root, _, filenames in os.walk(base_path):
        files += [os.path.join(root, f) for f in filenames if is_flex2_eeg_file(f)]
    if subjects:
        wanted = set(subjects)
        files = [f for f in files if wanted & set(os.path.relpath(f, base_path).split(os.sep))]
    return sorted(files)


# ==========================================
# MAIN EXECUTION
# ==========================================
def default_n_jobs():
    """Number of parallel workers, limited by CPU cores and available RAM."""
    try:
        available_cores = len(os.sched_getaffinity(0))
    except AttributeError:  # Windows / macOS
        available_cores = os.cpu_count() or 1

    n_jobs = min(available_cores, MAX_CONCURRENT_JOBS)
    try:
        total_ram_gb = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES') / 1024**3
        n_jobs = min(n_jobs, int(total_ram_gb // EST_GB_PER_JOB))
    except (AttributeError, ValueError, OSError):
        pass
    return available_cores, max(1, n_jobs)


def parse_args():
    parser = argparse.ArgumentParser(description="EEG preprocessing of Emotiv FLEX2 recordings (bad channels/segments + ICA/ICLabel).")
    parser.add_argument("--data-path", default=BASE_PATH,
                        help="Folder that is searched recursively for *FLEX2*.csv files (env: EEG_DATA_PATH). "
                             "Default: %(default)s")
    parser.add_argument("--output-dir", default=OUTPUT_DIR,
                        help="Folder for the cleaned .fif files, one per CAVIR phase: "
                             "<year>/<participant>/CAVIR_Start<N>/eeg/ and CAVIR_Baseline/eeg/ "
                             "(env: EEG_OUTPUT_DIR). Default: %(default)s")
    parser.add_argument("--log-dir", default=LOG_DIR,
                        help="Folder for the log file (env: EEG_LOG_DIR). Default: %(default)s")
    parser.add_argument("--jobs", "-j", type=int, default=None,
                        help="Number of parallel workers (env: EEG_N_JOBS). "
                             "Default: limited by CPU cores and RAM (~%d GB per job)." % EST_GB_PER_JOB)
    parser.add_argument("--subjects", nargs="+", default=None,
                        help="Only process recordings inside these subject folders (default: all).")
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    base_path = os.path.abspath(os.path.expanduser(args.data_path))
    output_dir = os.path.abspath(os.path.expanduser(args.output_dir))
    log_dir = os.path.abspath(os.path.expanduser(args.log_dir))

    # Initialize logger for the Main Process
    configure_logger(log_dir)

    mne.set_log_level('WARNING')
    logging.getLogger('pyprep').setLevel(logging.ERROR)  # hides repeated 'ransac' notices

    # Core Detection
    available_cores, N_JOBS = default_n_jobs()
    env_jobs = os.environ.get("EEG_N_JOBS")
    if args.jobs is not None:
        N_JOBS = max(1, args.jobs)
    elif env_jobs:
        N_JOBS = max(1, int(env_jobs))

    logging.info(f"------------------------------------------------")
    logging.info(f"SYSTEM: {available_cores} Cores Detected.")
    logging.info(f"CONFIG: Running {N_JOBS} Parallel Jobs (Safety Cap: {MAX_CONCURRENT_JOBS})")
    logging.info(f"DATA:   {base_path}")
    logging.info(f"OUTPUT: {output_dir}")
    logging.info(f"LOG:    {os.path.join(log_dir, LOG_FILE)}")
    logging.info(f"------------------------------------------------")

    if not os.path.isdir(base_path):
        logging.error(f"Base path not found: {base_path} (set it with --data-path or EEG_DATA_PATH)")
        sys.exit(1)

    eeg_files = find_eeg_files(base_path, args.subjects)
    logging.info(f"Found {len(eeg_files)} {EEG_FILE_TAG} recordings. Launching workers...")

    # Joblib Execution
    Parallel(n_jobs=min(N_JOBS, max(1, len(eeg_files))))(
        delayed(process_file)(f, base_path, output_dir, log_dir) for f in eeg_files
    )

    logging.info("Run Finished.")
