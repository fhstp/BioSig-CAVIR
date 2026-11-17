"""
GSR processing functions for baseline calculation and phasic response detection.
Extracted from lucas.py and adapted for the pipeline structure.
"""
import pandas as pd
import numpy as np


def calculate_baseline_and_deviations(data, baseline_col='GSR_CONDUCTANCE', 
                                      min_deviation=0.1, max_deviation=3.0):
    """
    Calculate baseline (minimum value) and deviations from baseline.
    
    Parameters
    ----------
    data : pd.DataFrame
        GSR data with conductance column
    baseline_col : str, default 'GSR_CONDUCTANCE'
        Column name containing GSR conductance values
    min_deviation : float, default 0.1
        Minimum deviation (µS) to consider as phasic response
    max_deviation : float, default 3.0
        Maximum deviation (µS) to consider as phasic response
    
    Returns
    -------
    baseline : float
        Baseline conductance value (minimum)
    data_with_deviations : pd.DataFrame
        Original data with added 'deviation' column
    phasic_data : pd.DataFrame
        Filtered data containing only phasic responses
    """
    # Identify the baseline (minimum value)
    baseline = data[baseline_col].min()
    
    # Calculate the deviation from the baseline
    data_with_deviations = data.copy()
    data_with_deviations['deviation'] = data_with_deviations[baseline_col] - baseline
    
    # Filter the data to include only phasic responses
    phasic_data = data_with_deviations[
        (data_with_deviations['deviation'] >= min_deviation) & 
        (data_with_deviations['deviation'] <= max_deviation)
    ].copy()
    
    return baseline, data_with_deviations, phasic_data


def categorize_deviations(phasic_data, bins=None, categories=None):
    """
    Categorize phasic response deviations into bins.
    
    Parameters
    ----------
    phasic_data : pd.DataFrame
        Data containing 'deviation' column
    bins : list, optional
        Bin edges for categorization. Default: [0, 0.5, 1.0, 2.0, 3.0, 10]
    categories : list, optional
        Category labels. Default: ['Very Low', 'Low', 'High', 'Very High', 'Extremely High']
    
    Returns
    -------
    pd.DataFrame
        Data with added 'category' column
    """
    if bins is None:
        bins = [0, 0.5, 1.0, 2.0, 3.0, 10]
    if categories is None:
        categories = ['Very Low', 'Low', 'High', 'Very High', 'Extremely High']
    
    # Categorize deviations based on these ranges
    phasic_data = phasic_data.copy()
    phasic_data['category'] = pd.cut(
        phasic_data['deviation'], 
        bins=bins, 
        labels=categories, 
        right=False
    )
    
    return phasic_data

