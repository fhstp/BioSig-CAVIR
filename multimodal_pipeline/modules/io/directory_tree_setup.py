import os, time, json
from datetime import datetime




def make_run_root(base_results="results", label=None, use_epoch=False):
    """
    Creates a unique run directory under 'results/'.
    Adds a metadata file.
    Change epoch to true for UNIX time.
    Optional label: 'results/1731062458' or 'results/20251108_112530_label'.
    """
    ts = str(int(time.time())) if use_epoch else datetime.now().strftime("%Y%m%d_%H%M%S")
    suffix = f"_{label}" if label else ""
    run_root = os.path.join(base_results, f"{ts}{suffix}")

    os.makedirs(run_root, exist_ok=False)  # fail if somehow already exists

    meta = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "epoch": int(time.time()),
        "label": label,

    }
    # TODO add more information to metadata for entire setup here ? Like participats and tasks etc? 

    with open(os.path.join(run_root, "run_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)

    return run_root



def validate_order(order):
    """ Checks if order is a valid permutation of 'PTM' """
    order = order.upper().strip()
    if sorted(order) != ["M", "P", "T"]:
        raise ValueError(f"Invalid view '{order}'. Must be a permutation of 'PTM'.")
    return order




def build_result_dir(root, pid, task, metric, order="PTM"):
    """ Builds a directory path for storing results """
    order = validate_order(order)
    name_for = {"P": str(pid), "T": str(task), "M": str(metric)}
    parts = [name_for[c] for c in order]
    return os.path.join(root, *parts)



def ensure_result_dirs(run_root, participants, tasks, metrics, order="PTM"):
    """ Creates the complete directory tree """
    for pid in participants:
        for task in tasks:
            for metric in metrics:
                d = build_result_dir(run_root, pid, task, metric, order)
                os.makedirs(d, exist_ok=True)  # creates the tree

