from __future__ import annotations
import numpy as np
import pandas as pd





def resolve_ivt_params(et_params: dict) -> dict:
    seg = (et_params or {}).get("segmentation", {}) or {}

    # defaults (your current ones)
    p = {
        "velocity_threshold": seg.get("velocity_threshold_deg_s", 30),
        "min_fixation_duration_ms": seg.get("min_fixation_duration_ms", 60),
        "min_saccade_duration_ms": seg.get("min_saccade_duration_ms", 22),
        "three_state": seg.get("three_state", False),
        "min_mid_duration_ms": seg.get("min_mid_duration_ms", 80),
        "use_hysteresis": seg.get("use_hysteresis", False),
        "fixation_on_threshold": seg.get("fixation_on_threshold", None),
        "fixation_off_threshold": seg.get("fixation_off_threshold", None),
        "saccade_on_threshold": seg.get("saccade_on_threshold", None),
        "saccade_off_threshold": seg.get("saccade_off_threshold", None),
        "smooth_win_ms": seg.get("smooth_win_ms", 0),
        "merge_fix_gap_ms": seg.get("merge_fix_gap_ms", 0),
    }

    # sanity checks (fail fast)
    if p["velocity_threshold"] <= 0:
        raise ValueError("velocity_threshold_deg_s must be > 0")

    if p["min_fixation_duration_ms"] < 0 or p["min_saccade_duration_ms"] < 0:
        raise ValueError("min durations must be >= 0")

    if p["use_hysteresis"]:
        needed = ["fixation_on_threshold", "fixation_off_threshold", "saccade_on_threshold", "saccade_off_threshold"]
        missing = [k for k in needed if p[k] is None]
        if missing:
            raise ValueError(f"use_hysteresis=True but missing: {missing}")

    return p




def apply_ivt_segmentation(
    df: pd.DataFrame,
    *,
    vel_col: str,
    out_fix_col: str = "fix",
    out_sac_col: str = "sac",
    valid_col: str | None = "valid_sample",   # set None to ignore validity
    sampling_rate_hz: float | None = None,
    # pass-through params
    velocity_threshold: float = 30.0,
    min_fixation_duration_ms: float = 60.0,
    min_saccade_duration_ms: float = 0.0,
    min_mid_duration_ms: float = 0.0,
    three_state: bool = False,
    use_hysteresis: bool = False,
    fixation_off_threshold: float | None = None,
    fixation_on_threshold: float | None = None,
    saccade_off_threshold: float | None = None,
    saccade_on_threshold: float | None = None,
    fixation_max_velocity: float | None = None,
    saccade_min_velocity: float | None = None,
    smooth_win_ms: float = 0.0,
    merge_fix_gap_ms: float = 0.0,
) -> pd.DataFrame:
    """
    Apply I-VT segmentation to a dataframe. Adds fixation/saccade columns and returns df copy.
    """
    if vel_col not in df.columns:
        raise KeyError(f"Velocity column '{vel_col}' not found. Available: {list(df.columns)}")

    out = df.copy()
    vel = pd.to_numeric(out[vel_col], errors="coerce").to_numpy()

    # Optionally gate by validity: do not classify invalid samples
    if valid_col is not None and valid_col in out.columns:
        valid = out[valid_col].fillna(False).astype(bool).to_numpy()
        vel_for_classify = vel.copy()
        vel_for_classify[~valid] = np.nan
    else:
        vel_for_classify = vel

    fix, sac = create_fixation_saccade_arrays(
        gaze_velocity=vel_for_classify,
        velocity_threshold=velocity_threshold,
        min_fixation_duration_ms=min_fixation_duration_ms,
        sampling_rate_hz=sampling_rate_hz,
        three_state=three_state,
        use_hysteresis=use_hysteresis,
        fixation_off_threshold=fixation_off_threshold,
        fixation_on_threshold=fixation_on_threshold,
        saccade_off_threshold=saccade_off_threshold,
        saccade_on_threshold=saccade_on_threshold,
        fixation_max_velocity=fixation_max_velocity,
        saccade_min_velocity=saccade_min_velocity,
        min_saccade_duration_ms=min_saccade_duration_ms,
        min_mid_duration_ms=min_mid_duration_ms,
        smooth_win_ms=smooth_win_ms,
        merge_fix_gap_ms=merge_fix_gap_ms,
    )

    out[out_fix_col] = fix.astype(int)
    out[out_sac_col] = sac.astype(int)

    return out






def create_fixation_saccade_arrays(
    gaze_velocity: np.ndarray,
    *,
    sampling_rate_hz: float,
    velocity_threshold: float = 30.0,  # used in single-threshold mode
    # 3-state & hysteresis knobs
    three_state: bool = False,
    use_hysteresis: bool = False,
    fixation_off_threshold: float | None = None,
    fixation_on_threshold: float | None = None,
    saccade_off_threshold: float | None = None,
    saccade_on_threshold: float | None = None,
    fixation_max_velocity: float | None = None,
    saccade_min_velocity: float | None = None,
    min_fixation_duration_ms: float = 60.0,
    min_saccade_duration_ms: float = 0.0,
    min_mid_duration_ms: float = 0.0,
    smooth_win_ms: float = 0.0,
    merge_fix_gap_ms: float = 0.0,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Cleaned version of your create_fixation_saccade_arrays2 with identical behavior.
    Returns: fixation_mask (0/1), saccade_mask (0/1)
    """
    vel = np.asarray(gaze_velocity, float)
    N = len(vel)
    fix = np.zeros(N, dtype=int)
    sac = np.zeros(N, dtype=int)
    if N == 0:
        return fix, sac
    if sampling_rate_hz <= 0:
        raise ValueError("sampling_rate_hz must be > 0")

    # smoothing
    ms_per_sample = 1000.0 / sampling_rate_hz
    def moving_avg(x, k):
        if k <= 1: return x
        w = np.ones(k) / k
        return np.convolve(x, w, mode="same")

    k = int(round(smooth_win_ms / ms_per_sample))
    if k % 2 == 0: k = max(1, k + 1)
    vel_sm = moving_avg(vel, k) if k > 1 else vel

    min_fix_len = int(np.ceil(max(0.0, min_fixation_duration_ms) / ms_per_sample))
    min_sac_len = int(np.ceil(max(0.0, min_saccade_duration_ms) / ms_per_sample))
    min_mid_len = int(np.ceil(max(0.0, min_mid_duration_ms) / ms_per_sample))
    gap_len     = int(np.floor(max(0.0, merge_fix_gap_ms) / ms_per_sample))
    finite = np.isfinite(vel_sm)

    def runs(mask):
        out = []
        on = False; s = 0
        for i, m in enumerate(mask):
            if m and not on:
                on = True; s = i
            elif not m and on:
                on = False; out.append((s, i-1))
        if on: out.append((s, len(mask)-1))
        return out

    # 3-state mode
    if three_state:
        if use_hysteresis:
            if fixation_off_threshold is None or fixation_on_threshold is None:
                raise ValueError("three_state+hysteresis: set fixation_off_threshold & fixation_on_threshold")
            if saccade_off_threshold is None or saccade_on_threshold is None:
                raise ValueError("three_state+hysteresis: set saccade_off_threshold & saccade_on_threshold")
            if not (fixation_off_threshold < fixation_on_threshold):
                raise ValueError("fixation_off_threshold must be < fixation_on_threshold")
            if not (saccade_off_threshold < saccade_on_threshold):
                raise ValueError("saccade_off_threshold must be < saccade_on_threshold")
            if not (fixation_on_threshold <= saccade_off_threshold):
                raise ValueError("Require fixation_on_threshold <= saccade_off_threshold")

            FIX, MID, SAC = 0, 1, 2
            state = FIX
            states = np.full(N, MID, dtype=int)

            for i in range(N):
                v = vel_sm[i]
                if not finite[i]:
                    states[i] = MID
                    continue
                if state == FIX and v >= fixation_on_threshold:
                    state = MID
                elif state == MID and v < fixation_off_threshold:
                    state = FIX
                elif state == MID and v >= saccade_on_threshold:
                    state = SAC
                elif state == SAC and v < saccade_off_threshold:
                    state = MID
                states[i] = state
        else:
            low  = fixation_max_velocity if fixation_max_velocity is not None else velocity_threshold
            high = saccade_min_velocity  if saccade_min_velocity  is not None else velocity_threshold
            states = np.full(N, 1, dtype=int)
            states[(vel_sm <  low) & finite] = 0
            states[(vel_sm >= high) & finite] = 2

        # enforce mins
        fix_mask = np.zeros(N, dtype=bool)
        for s, e in runs(states == 0):
            if (e - s + 1) >= min_fix_len:
                fix_mask[s:e+1] = True
        sac_mask = np.zeros(N, dtype=bool)
        for s, e in runs(states == 2):
            if (e - s + 1) >= min_sac_len:
                sac_mask[s:e+1] = True

        fix[fix_mask] = 1
        sac[sac_mask] = 1

    else:
        # Binary I-VT (with optional hysteresis)
        if use_hysteresis:
            if saccade_off_threshold is None: saccade_off_threshold = velocity_threshold
            if saccade_on_threshold  is None: saccade_on_threshold  = velocity_threshold
            IN_FIX, IN_SAC = 0, 1
            state = IN_FIX
            run_start = 0

            def close_run(st, s, e):
                if e < s: return
                if st == IN_FIX:
                    if (e - s + 1) >= min_fix_len: fix[s:e+1] = 1
                else:
                    if (e - s + 1) >= min_sac_len: sac[s:e+1] = 1

            for i in range(N):
                v = vel_sm[i]
                if not finite[i]:
                    close_run(state, run_start, i-1)
                    state = IN_FIX; run_start = i + 1
                    continue
                if state == IN_FIX and v >= saccade_on_threshold:
                    close_run(IN_FIX, run_start, i-1); state = IN_SAC; run_start = i
                elif state == IN_SAC and v < saccade_off_threshold:
                    close_run(IN_SAC, run_start, i-1); state = IN_FIX; run_start = i
            close_run(state, run_start, N-1)
        else:
            is_sac = (vel_sm >= velocity_threshold) & finite
            is_fix = (~is_sac) & finite
            for s, e in runs(is_fix):
                if (e - s + 1) >= min_fix_len: fix[s:e+1] = 1
            for s, e in runs(is_sac):
                if (e - s + 1) >= min_sac_len: sac[s:e+1] = 1

    # Merge tiny fixation gaps if requested
    if gap_len > 0:
        changed = True
        while changed:
            changed = False
            fr = [(s, e) for s, e in runs(fix.astype(bool))]
            for (s1, e1), (s2, e2) in zip(fr, fr[1:]):
                gap = s2 - e1 - 1
                if 0 < gap <= gap_len:
                    fix[e1+1:s2] = 1
                    sac[e1+1:s2] = 0
                    changed = True
                    break

    sac[fix == 1] = 0
    return fix, sac
