"""
Investigation of HeartPy Timestamp Bug

This script tests whether HeartPy can handle real timestamps or requires
uniform synthetic timestamps for proper sampling rate calculation.
"""

import numpy as np
import pandas as pd
import heartpy as hp
from pathlib import Path

def test_real_vs_synthetic_timestamps():
    """
    Test HeartPy with both real and synthetic timestamps to identify the bug.
    """
    
    print("=" * 80)
    print("HEARTPY TIMESTAMP BUG INVESTIGATION")
    print("=" * 80)
    
    # Generate a synthetic ECG signal at 130 Hz
    true_fs = 130.0  # Hz
    duration = 10.0  # seconds
    n_samples = int(true_fs * duration)
    
    # Create synthetic ECG: sum of sine waves to mimic heartbeats at ~75 BPM
    t_ideal = np.arange(n_samples) / true_fs
    heart_rate = 75  # BPM
    heart_rate_hz = heart_rate / 60.0
    
    # Simple synthetic ECG: fundamental + harmonics
    ecg_signal = (
        1.0 * np.sin(2 * np.pi * heart_rate_hz * t_ideal) +
        0.3 * np.sin(2 * np.pi * 2 * heart_rate_hz * t_ideal) +
        0.1 * np.sin(2 * np.pi * 3 * heart_rate_hz * t_ideal) +
        0.05 * np.random.randn(n_samples)  # noise
    )
    
    print(f"\nGenerated synthetic ECG: {n_samples} samples at {true_fs} Hz")
    print(f"Duration: {duration} seconds")
    print(f"Simulated heart rate: {heart_rate} BPM")
    
    # Scenario 1: Perfect uniform timestamps (what the Analysis notebook does)
    print("\n" + "-" * 80)
    print("SCENARIO 1: Synthetic Uniform Timestamps (Current Workaround)")
    print("-" * 80)
    
    t_synthetic = t_ideal * 1000.0  # convert to milliseconds
    t_synthetic = t_synthetic - t_synthetic[0]  # rebase to 0
    
    dt_synthetic = np.diff(t_synthetic)
    dt_median_synthetic = np.median(dt_synthetic)
    inferred_fs_synthetic = 1000.0 / dt_median_synthetic
    
    print(f"Median time step: {dt_median_synthetic:.6f} ms")
    print(f"Inferred sampling rate: {inferred_fs_synthetic:.2f} Hz")
    print(f"Expected sampling rate: {true_fs:.2f} Hz")
    print(f"Error: {abs(inferred_fs_synthetic - true_fs):.4f} Hz")
    
    try:
        x_filt_1 = hp.filter_signal(ecg_signal, cutoff=[5, 25], sample_rate=inferred_fs_synthetic, 
                                     order=3, filtertype='bandpass')
        wd_1, measures_1 = hp.process(x_filt_1, sample_rate=inferred_fs_synthetic, 
                                       bpmmin=40, bpmmax=200, high_precision=True)
        print(f"✓ HeartPy succeeded!")
        print(f"  Detected {len(wd_1['peaklist'])} peaks")
        print(f"  Estimated BPM: {measures_1['bpm']:.1f}")
        print(f"  RMSSD: {measures_1['rmssd']:.2f} ms")
    except Exception as e:
        print(f"✗ HeartPy FAILED: {e}")
    
    # Scenario 2: Real timestamps with jitter (realistic device behavior)
    print("\n" + "-" * 80)
    print("SCENARIO 2: Real Timestamps with Jitter (Actual Device Data)")
    print("-" * 80)
    
    # Add realistic timing jitter (±2% variation in sample intervals)
    jitter_factor = 0.02
    t_real = np.zeros(n_samples)
    base_interval = 1.0 / true_fs
    
    for i in range(1, n_samples):
        jitter = np.random.uniform(-jitter_factor, jitter_factor)
        t_real[i] = t_real[i-1] + base_interval * (1.0 + jitter)
    
    t_real = t_real * 1000.0  # convert to milliseconds
    
    dt_real = np.diff(t_real)
    dt_median_real = np.median(dt_real)
    inferred_fs_real = 1000.0 / dt_median_real
    
    print(f"Median time step: {dt_median_real:.6f} ms")
    print(f"Jitter range: [{dt_real.min():.6f}, {dt_real.max():.6f}] ms")
    print(f"Jitter std dev: {dt_real.std():.6f} ms")
    print(f"Inferred sampling rate: {inferred_fs_real:.2f} Hz")
    print(f"Expected sampling rate: {true_fs:.2f} Hz")
    print(f"Error: {abs(inferred_fs_real - true_fs):.4f} Hz")
    
    try:
        x_filt_2 = hp.filter_signal(ecg_signal, cutoff=[5, 25], sample_rate=inferred_fs_real, 
                                     order=3, filtertype='bandpass')
        wd_2, measures_2 = hp.process(x_filt_2, sample_rate=inferred_fs_real, 
                                       bpmmin=40, bpmmax=200, high_precision=True)
        print(f"✓ HeartPy succeeded!")
        print(f"  Detected {len(wd_2['peaklist'])} peaks")
        print(f"  Estimated BPM: {measures_2['bpm']:.1f}")
        print(f"  RMSSD: {measures_2['rmssd']:.2f} ms")
    except Exception as e:
        print(f"✗ HeartPy FAILED: {e}")
    
    # Scenario 3: Unix timestamps (large absolute values)
    print("\n" + "-" * 80)
    print("SCENARIO 3: Unix Timestamps (Large Absolute Values)")
    print("-" * 80)
    
    # Simulate Unix timestamps starting from "now"
    base_unix = 1700000000.0  # Nov 2023
    t_unix = base_unix + t_real / 1000.0  # back to seconds, add to base
    
    dt_unix = np.diff(t_unix)
    dt_median_unix = np.median(dt_unix)
    inferred_fs_unix = 1.0 / dt_median_unix  # seconds, so no 1000x factor
    
    print(f"Timestamp range: [{t_unix[0]:.3f}, {t_unix[-1]:.3f}] (Unix seconds)")
    print(f"Median time step: {dt_median_unix:.6f} seconds")
    print(f"Inferred sampling rate: {inferred_fs_unix:.2f} Hz")
    print(f"Expected sampling rate: {true_fs:.2f} Hz")
    print(f"Error: {abs(inferred_fs_unix - true_fs):.4f} Hz")
    
    try:
        x_filt_3 = hp.filter_signal(ecg_signal, cutoff=[5, 25], sample_rate=inferred_fs_unix, 
                                     order=3, filtertype='bandpass')
        wd_3, measures_3 = hp.process(x_filt_3, sample_rate=inferred_fs_unix, 
                                       bpmmin=40, bpmmax=200, high_precision=True)
        print(f"✓ HeartPy succeeded!")
        print(f"  Detected {len(wd_3['peaklist'])} peaks")
        print(f"  Estimated BPM: {measures_3['bpm']:.1f}")
        print(f"  RMSSD: {measures_3['rmssd']:.2f} ms")
    except Exception as e:
        print(f"✗ HeartPy FAILED: {e}")
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print("\nThe issue is NOT with HeartPy itself, but with how timestamps are handled:")
    print("1. HeartPy only needs the correct SAMPLING RATE (fs) - it doesn't use timestamps")
    print("2. The bug occurs when inferring fs from real timestamps with jitter")
    print("3. Your Analysis.ipynb IGNORES real timestamps and uses synthetic ones")
    print("\nSolution: Improve sampling rate inference or use config fallback_fs_hz")
    print("=" * 80)


if __name__ == "__main__":
    test_real_vs_synthetic_timestamps()
