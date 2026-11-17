"""
GSR metrics calculation.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def mean_phasic_response(phasic_data: pd.DataFrame, deviation_col='deviation') -> float:
    """
    Calculate mean phasic response amplitude.
    
    Parameters
    ----------
    phasic_data : pd.DataFrame
        Data containing phasic responses
    deviation_col : str, default 'deviation'
        Column name for deviation values
    
    Returns
    -------
    float
        Mean phasic response in µS
    """
    if deviation_col not in phasic_data.columns:
        return np.nan
    deviations = phasic_data[deviation_col].values
    deviations = deviations[np.isfinite(deviations)]
    if deviations.size == 0:
        return np.nan
    return float(np.mean(deviations))


def max_phasic_response(phasic_data: pd.DataFrame, deviation_col='deviation') -> float:
    """
    Calculate maximum phasic response amplitude.
    
    Parameters
    ----------
    phasic_data : pd.DataFrame
        Data containing phasic responses
    deviation_col : str, default 'deviation'
        Column name for deviation values
    
    Returns
    -------
    float
        Maximum phasic response in µS
    """
    if deviation_col not in phasic_data.columns:
        return np.nan
    deviations = phasic_data[deviation_col].values
    deviations = deviations[np.isfinite(deviations)]
    if deviations.size == 0:
        return np.nan
    return float(np.max(deviations))


def phasic_response_count(phasic_data: pd.DataFrame) -> int:
    """
    Count the number of phasic responses.
    
    Parameters
    ----------
    phasic_data : pd.DataFrame
        Data containing phasic responses
    
    Returns
    -------
    int
        Number of phasic response samples
    """
    return len(phasic_data) if phasic_data is not None and len(phasic_data) > 0 else 0


def mean_baseline(data: pd.DataFrame, baseline_col='GSR_CONDUCTANCE') -> float:
    """
    Calculate mean baseline (tonic) GSR level.
    
    Parameters
    ----------
    data : pd.DataFrame
        GSR data
    baseline_col : str, default 'GSR_CONDUCTANCE'
        Column name for conductance values
    
    Returns
    -------
    float
        Mean baseline conductance in µS
    """
    if baseline_col not in data.columns:
        return np.nan
    values = pd.to_numeric(data[baseline_col], errors='coerce').values
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.nan
    return float(np.mean(values))


def std_baseline(data: pd.DataFrame, baseline_col='GSR_CONDUCTANCE') -> float:
    """
    Calculate standard deviation of baseline (tonic) GSR level.
    
    Parameters
    ----------
    data : pd.DataFrame
        GSR data
    baseline_col : str, default 'GSR_CONDUCTANCE'
        Column name for conductance values
    
    Returns
    -------
    float
        Standard deviation of baseline conductance in µS
    """
    if baseline_col not in data.columns:
        return np.nan
    values = pd.to_numeric(data[baseline_col], errors='coerce').values
    values = values[np.isfinite(values)]
    if values.size == 0:
        return np.nan
    return float(np.std(values, ddof=1))


_METRIC_FUNCS = {
    "MEAN_PHASIC": mean_phasic_response,
    "MAX_PHASIC": max_phasic_response,
    "PHASIC_COUNT": phasic_response_count,
    "MEAN_BASELINE": mean_baseline,
    "STD_BASELINE": std_baseline,
}


def compute_gsr_metrics(
    data: pd.DataFrame,
    phasic_data: pd.DataFrame,
    metrics: list[str],
    baseline_col: str = 'GSR_CONDUCTANCE',
    deviation_col: str = 'deviation'
) -> dict[str, float]:
    """
    Compute selected GSR metrics.
    
    Parameters
    ----------
    data : pd.DataFrame
        Full GSR data with baseline
    phasic_data : pd.DataFrame
        Phasic response data
    metrics : list[str]
        List of metric names to compute
    baseline_col : str, default 'GSR_CONDUCTANCE'
        Column name for baseline values
    deviation_col : str, default 'deviation'
        Column name for deviation values
    
    Returns
    -------
    dict[str, float]
        Dictionary of computed metrics
    """
    results: dict[str, float] = {}
    
    for name in metrics:
        name_upper = name.upper()
        func = _METRIC_FUNCS.get(name_upper)
        if func is None:
            continue
        
        # Some metrics need phasic_data, others need full data
        if name_upper in ["MEAN_PHASIC", "MAX_PHASIC", "PHASIC_COUNT"]:
            if name_upper == "PHASIC_COUNT":
                results[name] = float(func(phasic_data))
            else:
                results[name] = func(phasic_data, deviation_col=deviation_col)
        else:
            results[name] = func(data, baseline_col=baseline_col)
    
    return results

