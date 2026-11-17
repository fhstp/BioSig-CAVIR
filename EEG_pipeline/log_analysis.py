import re
import matplotlib
matplotlib.use("Agg")  # headless: only saves PNGs, no window needed
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import os

# Paths are relative to this script by default; override with
# EEG_LOG_DIR (same variable script.py uses) or EEG_LOG_FILE / EEG_ANALYSIS_DIR.
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.environ.get("EEG_LOG_DIR", os.path.join(SCRIPT_DIR, "logs"))
LOG_FILE = os.environ.get("EEG_LOG_FILE", os.path.join(LOG_DIR, "preprocessing.log"))
OUT_DIR = os.environ.get("EEG_ANALYSIS_DIR", os.path.join(LOG_DIR, "analysis_output"))
os.makedirs(OUT_DIR, exist_ok=True)

print(f"Reading log file: {LOG_FILE}...")

# Result lines written by script.py, e.g.
#   ... - INFO - SUCCESS: 2026_USTP/<id>/CAVIR/<rec>.md.bp.csv -> /path/<rec>_preprocessed_raw.fif [...]
#   ... - ERROR - FAIL: 2026_USTP/<id>/CAVIR/<rec>.md.bp.csv -> Too many bad channels: 4/14
#   ... - ERROR - CRASH: 2026_USTP/<id>/CAVIR/<rec>.md.bp.csv -> <exception>
result_pattern = re.compile(r"\b(SUCCESS|FAIL|CRASH):\s+(.+?)\s+->\s+(.*)$")

error_categories = {
    "Too many bad channels": re.compile(r"Too many bad channels", re.IGNORECASE),
    "Too little clean data": re.compile(r"Too little clean data", re.IGNORECASE),
    "Bad-channel detection failed": re.compile(r"Bad-channel detection failed|PyPREP Failed", re.IGNORECASE),
    "ICA Failed": re.compile(r"ICA Failed", re.IGNORECASE),
}

rows = []
with open(LOG_FILE, "r", encoding="utf-8") as f:
    for line in f:
        m = result_pattern.search(line.strip())
        if not m:
            continue
        kind, file_id, detail = m.groups()
        if kind == "SUCCESS":
            reason = "None"
        elif kind == "CRASH":
            reason = "Crash (read/save error)"
        else:
            reason = next((name for name, pat in error_categories.items() if pat.search(detail)), "Other")
        rows.append({
            "Subject": os.path.dirname(file_id) or file_id,
            "File": file_id,
            "Status": "Success" if kind == "SUCCESS" else "Failed",
            "Reason": reason,
            "Detail": detail,
        })

df = pd.DataFrame(rows)

if df.empty:
    print("No results found! Check log file path.")
    exit()

df = df.drop_duplicates(subset="File", keep="last")

total = len(df)
n_success = (df["Status"] == "Success").sum()
n_failed = total - n_success

print(f"\n{'='*40}")
print(f"PREPROCESSING REPORT")
print(f"{'='*40}")
print(f"Files processed: {total}")
print(f"Subjects:        {df['Subject'].nunique()}")
print(f"Success:         {n_success} ({n_success / total * 100:.1f}%)")
print(f"Failed:          {n_failed} ({n_failed / total * 100:.1f}%)")

failed = df[df["Status"] == "Failed"]
csv_path = os.path.join(OUT_DIR, "failed_files.csv")
if not failed.empty:
    print("\n--- Failure reasons ---")
    print(failed["Reason"].value_counts().to_string())
    failed[["File", "Reason", "Detail"]].to_csv(csv_path, index=False)
    print(f"\n List of failed files saved to: {csv_path}")
else:
    print("\n No failed files.")

sns.set_style("whitegrid")
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

status_counts = df["Status"].value_counts().reindex(["Success", "Failed"], fill_value=0)
ax1.pie(status_counts, labels=[f"{k} ({v})" for k, v in status_counts.items()],
        colors=["#66b3ff", "#ff9999"], autopct="%1.1f%%", startangle=90)
ax1.set_title("Preprocessing Outcome", fontsize=12, fontweight="bold")

if not failed.empty:
    reason_counts = failed["Reason"].value_counts()
    sns.barplot(x=reason_counts.values, y=reason_counts.index, color="#ff9999", ax=ax2)
    ax2.set_xlabel("Number of Files")
else:
    ax2.text(0.5, 0.5, "No failures", ha="center", va="center", fontsize=14)
    ax2.set_axis_off()
ax2.set_title("Failure Reasons", fontsize=12, fontweight="bold")

plt.tight_layout()
report_path = os.path.join(OUT_DIR, "preprocessing_report.png")
plt.savefig(report_path, dpi=150, bbox_inches="tight")
plt.close()

print(f"Visual report saved to: {report_path}")
