# Usability Evaluation Tasks (10-15 minutes)

## Purpose
Quick usability evaluation of the Multimodal Biosignal Analysis Pipeline. Total time: **10-15 minutes** (tasks + UEQ-S questionnaire).

## Target Participants
- Researchers working with biosignal data
- Basic Python familiarity required
- No prior experience with this pipeline needed

---

## Pre-Task Setup (Done BEFORE participant arrives)

### Prepare Demo Data Folder Structure
```
demo_data/
├── fe13ba43/
│   ├── RestingState_ECG.csv
│   ├── RestingState_Eyetracking.csv
│   └── RestingState_GSR.csv
└── ac7d92e1/
    ├── RestingState_ECG.csv
    ├── RestingState_Eyetracking.csv
    └── RestingState_GSR.csv
```

### Prepare Starter Notebook
Create `evaluation_session.ipynb` with:
```python
from modules.pipeline import run_pipeline

# Documentation available at:
# - docs/examples.md (quickstart)
# - docs/config_reference.md (all parameters)

# TODO: Complete the tasks below
```

### Session Setup (< 1 minute)
- Open `evaluation_session.ipynb` in Jupyter
- Show participant the `demo_data` folder
- Provide links to: `docs/examples.md` and `docs/config_reference.md`

---

## Evaluation Tasks (10 minutes total)

### Task 1: Basic Execution (4 minutes)
**Instruction given to participant:**

> "Get participant **fe13ba43** from folder **demo_data** and calculate the **RMSSD** metric and the **number of fixations**. Save the result with the label **'demo_1'**."

**Expected solution:**
```python
cfg = {
    "participants": ["fe13ba43"],
    "tasks": ["RestingState"],
    "metrics": {
        "ecg": ["RMSSD"],
        "eye_tracking": ["fixation_count"],
        "gsr": [],
        "head_movement": [],
    },
    "params": {
        "ecg": {"hr_outlier_range_bpm": [40, 200], "sampling_rate_hz": 250},
        "et": {"sampling_rate_hz": 120},
    },
    "input_path": "demo_data",
    "output_path": "results",
    "file_structure": "PTM",
    "label": "demo_1",
}

summary = run_pipeline(cfg)
print(summary)
```

**Success Criteria:**
- ✓ Pipeline runs without errors
- ✓ Participant can read the RMSSD and fixation_count values from output
- ✓ Completed within 4 minutes

**Observer Notes:**
- Used documentation? (yes/no, which docs?)
- Config structure intuitive? (yes/no)
- Any errors? (list)

---

### Task 2: Multi-Participant Analysis (3 minutes)
**Instruction:**

> "Now analyze **both participants** (fe13ba43 and ac7d92e1) and add the **mean_baseline** metric. Keep the same ECG and eye-tracking metrics. Use label **'demo_2'**."

**Expected changes:**
- `participants`: ["fe13ba43", "ac7d92e1"]
- `metrics.gsr`: ["mean_baseline"]
- `params.gsr`: {"baseline_col": "GSR_CONDUCTANCE"}
- `label`: "demo_2"

**Success Criteria:**
- ✓ Both participants analyzed
- ✓ All three modalities produce outputs
- ✓ Completed within 3 minutes

**Observer Notes:**
- Understood how to add modalities? (yes/no)
- Figured out params.gsr requirement? (yes/no, time taken)

---

### Task 3: Result Interpretation & Config Modification (3 minutes)
**Instruction:**

> "From your demo_2 results:
> 1. What is the RMSSD value for participant **ac7d92e1**?
> 2. Change the ECG sampling rate to **500 Hz** and re-run with label **'demo_3'**"

**Expected changes:**
- `params.ecg.sampling_rate_hz`: 500
- `label`: "demo_3"

**Success Criteria:**
- ✓ Can locate metric in summary DataFrame/output
- ✓ Successfully modifies parameter
- ✓ Completed within 3 minutes

**Observer Notes:**
- Output format understandable? (yes/no)
- Found parameter documentation? (yes/no)
- Understood where to modify sampling_rate_hz? (yes/no)

---

## UEQ-S Questionnaire (2-3 minutes)

### Instructions
"Please rate your experience with this pipeline on the following scales:"

**Scale:** 1 (left) to 7 (right)

| # | Negative | | | Neutral | | | Positive |
|---|----------|---|---|---------|---|---|----------|
| 1 | obstructive | 1 2 3 | 4 | 5 6 7 | supportive |
| 2 | complicated | 1 2 3 | 4 | 5 6 7 | easy |
| 3 | inefficient | 1 2 3 | 4 | 5 6 7 | efficient |
| 4 | confusing | 1 2 3 | 4 | 5 6 7 | clear |
| 5 | boring | 1 2 3 | 4 | 5 6 7 | exciting |
| 6 | not interesting | 1 2 3 | 4 | 5 6 7 | interesting |
| 7 | conventional | 1 2 3 | 4 | 5 6 7 | inventive |
| 8 | usual | 1 2 3 | 4 | 5 6 7 | leading edge |

**Dimensions measured:**
- **Pragmatic Quality** (items 1-4): usability, clarity, efficiency
- **Hedonic Quality** (items 5-8): excitement, interest, innovation

---

## Data Collection Template

### Participant Info
- ID: _______
- Role: [ ] Researcher [ ] Data Scientist [ ] Student [ ] Other: _______
- Python Level: [ ] Beginner [ ] Intermediate [ ] Advanced
- Biosignal Experience: [ ] None [ ] Basic [ ] Advanced
- Date: _______

### Task Performance
| Task | Time (min) | Success | Needed Help | Notes |
|------|------------|---------|-------------|-------|
| 1 - Basic | | ☐ | ☐ | |
| 2 - Multi | | ☐ | ☐ | |
| 3 - Modify | | ☐ | ☐ | |

### UEQ-S Scores
| Item | Score (1-7) |
|------|-------------|
| 1 | |
| 2 | |
| 3 | |
| 4 | |
| 5 | |
| 6 | |
| 7 | |
| 8 | |

**Pragmatic Quality Mean:** _______ (items 1-4)
**Hedonic Quality Mean:** _______ (items 5-8)

### Post-Task Questions (1 minute)
1. What was most confusing?
2. What worked well?
3. Any suggestions?

---

## Analysis Guidelines

### Success Metrics
- **Task completion rate:** % who completed each task successfully
- **Average time:** Per task
- **Help frequency:** How often intervention was needed
- **UEQ-S Pragmatic:** >4.0 is good, >5.0 is excellent
- **UEQ-S Hedonic:** >3.5 is good, >4.5 is excellent

### Minimum Sample Size
- **5 participants:** Identifies ~80% of major usability issues
- **8-10 participants:** Recommended for robust findings

### Red Flags to Watch For
- Task 1 takes >5 minutes (config too complex)
- Task 2 requires significant help (modality addition unclear)
- Pragmatic Quality <3.5 (serious usability issues)
- Participant cannot find metric values (output unclear)

---

## Evaluator Checklist

### Before Session
- [ ] Demo data prepared and validated
- [ ] Starter notebook created
- [ ] Documentation links work
- [ ] Timer ready
- [ ] Data collection sheet printed/ready

### During Session
- [ ] Encourage thinking aloud
- [ ] Note confusion points
- [ ] Only help if completely stuck (note it!)
- [ ] Time each task discreetly

### After Session
- [ ] Thank participant
- [ ] Transfer notes to spreadsheet
- [ ] Note environmental issues
- [ ] Update running analysis
