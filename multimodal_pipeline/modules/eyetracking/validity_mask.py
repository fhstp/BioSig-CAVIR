from __future__ import annotations
import numpy as np
import pandas as pd


def _has_cols(df: pd.DataFrame, cols: list[str]) -> bool:
    return all(c in df.columns for c in cols)


def add_validity_masks(
    df: pd.DataFrame,
    *,
    ts_col: str = "ts",
    pupil_min_mm: float = 0.5,
    pupil_max_mm: float = 12.0,
    gaze_dir_norm_bounds: tuple[float, float] = (0.5, 2.0),  # loose bounds
) -> pd.DataFrame:
    """
    Add validity masks to a unified eyetracking dataframe.

    This is feature-based:
    - If a signal group is missing, the corresponding mask is not created (or is all-False).
    - No rows are dropped. Masks are added as boolean columns.

    Expected canonical columns (if available):
      - ts
      - gaze_dir_l_x/y/z, gaze_dir_r_x/y/z (3D direction)
      - gaze_2d_x/y (2D gaze)
      - pupil_l_mm, pupil_r_mm
      - blink (optional provided)
      - confidence_* (optional)
    """
    out = df.copy()

    # ---- time validity ----
    if ts_col in out.columns:
        ts = pd.to_numeric(out[ts_col], errors="coerce")
        out["valid_ts"] = np.isfinite(ts.to_numpy())
    else:
        out["valid_ts"] = False

    # ---- gaze validity: 3D direction OR 2D gaze point ----
    # Left eye dir
    if _has_cols(out, ["gaze_dir_l_x", "gaze_dir_l_y", "gaze_dir_l_z"]):
        xl = pd.to_numeric(out["gaze_dir_l_x"], errors="coerce").to_numpy()
        yl = pd.to_numeric(out["gaze_dir_l_y"], errors="coerce").to_numpy()
        zl = pd.to_numeric(out["gaze_dir_l_z"], errors="coerce").to_numpy()
        norm_l = np.sqrt(xl**2 + yl**2 + zl**2)
        out["valid_gaze_l"] = np.isfinite(norm_l) & (norm_l >= gaze_dir_norm_bounds[0]) & (norm_l <= gaze_dir_norm_bounds[1])
        out["gaze_dir_norm_l"] = norm_l  # optional debug
    else:
        out["valid_gaze_l"] = False

    # Right eye dir
    if _has_cols(out, ["gaze_dir_r_x", "gaze_dir_r_y", "gaze_dir_r_z"]):
        xr = pd.to_numeric(out["gaze_dir_r_x"], errors="coerce").to_numpy()
        yr = pd.to_numeric(out["gaze_dir_r_y"], errors="coerce").to_numpy()
        zr = pd.to_numeric(out["gaze_dir_r_z"], errors="coerce").to_numpy()
        norm_r = np.sqrt(xr**2 + yr**2 + zr**2)
        out["valid_gaze_r"] = np.isfinite(norm_r) & (norm_r >= gaze_dir_norm_bounds[0]) & (norm_r <= gaze_dir_norm_bounds[1])
        out["gaze_dir_norm_r"] = norm_r  # optional debug
    else:
        out["valid_gaze_r"] = False

    # 2D gaze fallback (device might not have 3D)
    if _has_cols(out, ["gaze_2d_x", "gaze_2d_y"]):
        x2 = pd.to_numeric(out["gaze_2d_x"], errors="coerce")
        y2 = pd.to_numeric(out["gaze_2d_y"], errors="coerce")
        out["valid_gaze_2d"] = x2.notna() & y2.notna()

    # Combined gaze validity: any usable gaze signal
    gaze_valid_cols = ["valid_gaze_l", "valid_gaze_r"]
    if "valid_gaze_2d" in out.columns:
        gaze_valid_cols.append("valid_gaze_2d")
    out["valid_gaze"] = out[gaze_valid_cols].any(axis=1)

    # ---- pupil validity ----
    if "pupil_l_mm" in out.columns:
        pl = pd.to_numeric(out["pupil_l_mm"], errors="coerce")
        out["valid_pupil_l"] = pl.notna() & (pl >= pupil_min_mm) & (pl <= pupil_max_mm)
    else:
        out["valid_pupil_l"] = False

    if "pupil_r_mm" in out.columns:
        pr = pd.to_numeric(out["pupil_r_mm"], errors="coerce")
        out["valid_pupil_r"] = pr.notna() & (pr >= pupil_min_mm) & (pr <= pupil_max_mm)
    else:
        out["valid_pupil_r"] = False

    out["valid_pupil"] = out["valid_pupil_l"] | out["valid_pupil_r"]

    # ---- blink / track loss ----
    # If a blink column exists, trust it as "blink provided"
    if "blink" in out.columns:
        b = pd.to_numeric(out["blink"], errors="coerce").fillna(0)
        out["blink"] = (b > 0).astype(bool)
        out["valid_not_blink"] = ~out["blink"]
    else:
        out["valid_not_blink"] = True  # unknown, assume not blinking

    # A pragmatic "usable sample" mask:
    # - time must be valid
    # - gaze must be valid
    # - and not in blink (if provided)
    out["valid_sample"] = out["valid_ts"] & out["valid_gaze"] & out["valid_not_blink"]

    # Optional: a "track loss" proxy
    out["track_loss"] = out["valid_ts"] & (~out["valid_gaze"])

    return out


def validity_summary(df: pd.DataFrame) -> dict:
    """
    Fractions of samples per validity mask (output of add_validity_masks) for meta.json.

    track_loss_excl_blink_frac is the data-quality figure to report: blinks are
    expected signal loss and are reported separately as blink_time_prop.
    """
    def frac(mask) -> float | None:
        return float(np.mean(mask)) if len(df) else None

    blink = df["blink"].astype(bool) if "blink" in df.columns else pd.Series(False, index=df.index)
    out = {
        "valid_sample_frac": frac(df["valid_sample"]),
        "valid_gaze_frac": frac(df["valid_gaze"]),
        "valid_pupil_frac": frac(df["valid_pupil"]),
        "pupil_both_eyes_valid_frac": frac(df["valid_pupil_l"] & df["valid_pupil_r"]),
        "blink_time_prop": frac(blink),
        "track_loss_frac": frac(df["track_loss"]),
        "track_loss_excl_blink_frac": frac(df["track_loss"] & ~blink),
    }
    return out
