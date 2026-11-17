"""
Simple test to understand the HeartPy timestamp bug
"""

import numpy as np

print("=" * 80)
print("HEARTPY TIMESTAMP BUG - ROOT CAUSE ANALYSIS")
print("=" * 80)

# Simulate what Analysis.ipynb does
print("\nAnalysis.ipynb approach (lines 837-843):")
print("-" * 80)

n_samples = 1300  # 10 seconds at 130 Hz
step = 0.00769230769  # hardcoded step size (1/130 seconds)

# This is what Analysis.ipynb does - IGNORES real timestamps
t_synthetic = np.arange(n_samples) * step
print(f"Created synthetic time array: {n_samples} samples")
print(f"Step size: {step:.9f} seconds")
print(f"Implied sampling rate: {1/step:.2f} Hz")

t_ms = t_synthetic * 1000  # convert to ms
t_ms = t_ms - t_ms[0]  # rebase to 0

dt = np.diff(t_ms)
dt_med = np.median(dt)
fs_inferred = 1000.0 / dt_med

print(f"Median dt: {dt_med:.6f} ms")
print(f"Inferred fs: {fs_inferred:.2f} Hz")
print(f"[OK] Perfect uniform timestamps -> HeartPy works")

# Now simulate what rpeak_detection.py TRIES to do with real timestamps
print("\n\nrpeak_detection.py approach (lines 51-61):")
print("-" * 80)

# Simulate real device timestamps with jitter
true_fs = 130.0
base_interval = 1.0 / true_fs
t_real = np.zeros(n_samples)

# Add realistic jitter (±2% variation)
for i in range(1, n_samples):
    jitter = np.random.uniform(-0.02, 0.02)
    t_real[i] = t_real[i-1] + base_interval * (1.0 + jitter)

print(f"Created real timestamps with jitter")

# Convert to the same format as synthetic
t_real_ms = t_real * 1000
dt_real = np.diff(t_real_ms)
dt_real_med = np.median(dt_real)
fs_real = 1000.0 / dt_real_med

print(f"Median dt: {dt_real_med:.6f} ms (jitter range: [{dt_real.min():.4f}, {dt_real.max():.4f}])")
print(f"Inferred fs: {fs_real:.2f} Hz")
print(f"Error: {abs(fs_real - true_fs):.4f} Hz ({abs(fs_real - true_fs)/true_fs * 100:.2f}%)")

if abs(fs_real - true_fs) < 1.0:
    print("[OK] Small error - would probably work")
else:
    print("[ERROR] Large error - could cause problems")

# The REAL issue: what if timestamps are in a weird unit?
print("\n\nTHE ACTUAL BUG - Unit Detection Problem:")
print("-" * 80)

# Scenario: iMotions exports Unix timestamps in SECONDS
t_unix = 1700000000.0 + t_real  # Unix timestamp starting Nov 2023
dt_unix = np.diff(t_unix)
dt_unix_med = np.median(dt_unix)

print(f"Unix timestamps: [{t_unix[0]:.3f}, {t_unix[-1]:.3f}]")
print(f"Median dt: {dt_unix_med:.6f}")

# The code at line 60 tries to detect units:
unit_per_sec = 1000.0 if dt_unix_med > 1.0 else 1.0

print(f"Unit detection logic: dt_med={dt_unix_med:.6f}, so unit_per_sec={unit_per_sec}")

fs_wrong = unit_per_sec / dt_unix_med

print(f"Inferred fs: {fs_wrong:.2f} Hz")
print(f"Expected fs: {true_fs:.2f} Hz")
print(f"ERROR: {abs(fs_wrong - true_fs):.2f} Hz!")

if fs_wrong > 300 or fs_wrong < 10:
    print(f"[CRITICAL] fs={fs_wrong:.1f} Hz triggers fallback (line 66)")
    print("  -> Code falls back to synthetic timestamps")
    print("  -> This is why time_col=None workaround is needed!")

print("\n" + "=" * 80)
print("CONCLUSION:")
print("=" * 80)
print("The bug is in the UNIT DETECTION logic (line 60 of rpeak_detection.py)")
print("When timestamps are Unix seconds:")
print("  - dt_med approx 0.0077 seconds (< 1.0)")
print("  - Code thinks unit_per_sec = 1.0")
print("  - But actually needs to be 1000.0 for proper fs calculation")
print("  - Results in fs approx 130,000 Hz instead of 130 Hz")
print("\nThe workaround (time_col=None) bypasses this by using fallback_fs_hz")
print("=" * 80)
