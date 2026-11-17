import os, glob
import pandas as pd


    # FIXME the skip_title_line and read_csv_kwargs is jsut a workaround unti lthe eeg data will be handled by the preprocessing pipeline


def load_data_file(
    data_root,
    pid,
    task,
    modality,
    pattern="*{task}*{modality}*",
    sep=",",
    *,
    skip_title_line=False,
    read_csv_kwargs=None,
):
    """
    Find and load one delimited text file (CSV/TSV) for a participant, task, and modality.

    Parameters
    ----------
    data_root : str
        Root directory where all participant folders live (e.g. "data/").
    pid : str or int
        Participant ID (folder name).
    task : str
        Task name (e.g. "Cavir5").
    modality : str
        Modality keyword to look for in filenames (e.g. "ecg", "gsr", "eeg", "eye").
    pattern : str, optional
        Filename pattern (must include {task} and {modality} placeholders).
        Defaults to "*{task}*{modality}*" to allow .csv or .tsv extensions.
    sep : str, optional
        Field separator passed to pandas.read_csv. Defaults to ","; use "\t" for TSV files.

    Returns
    -------
    pd.DataFrame or None
        Loaded DataFrame if a matching file was found, otherwise None.
    """
    pdir = os.path.join(data_root, str(pid))
    if not os.path.isdir(pdir):
        print(f"[WARN] No folder for participant: {pdir}")
        return None

    search_pattern = os.path.join(pdir, pattern.format(task=task, modality=modality))
    matches = sorted(glob.glob(search_pattern))
    if not matches:
        print(
            f"[WARN] No {modality.upper()} file found for {pid} – {task}. "
            f"Search pattern: {search_pattern}"
        )
        return None

    # //TODO loading the first match - if there are several files with the same name for whatever reaosn it just picks the first match but maybe add some error handling
    file_path = matches[0]
    print(f"[INFO] Loading {modality.upper()} file: {file_path}")


    # FIXME that is jsut a workaround unti lthe eeg data will be handled by the preprocessing pipeline
    try:
        csv_kwargs = dict(read_csv_kwargs or {})
        if skip_title_line and "skiprows" not in csv_kwargs:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    first_line = f.readline()
                if first_line.startswith("title:"):
                    csv_kwargs["skiprows"] = 1
            except OSError:
                pass
        return pd.read_csv(file_path, sep=sep, **csv_kwargs)
    except Exception as e:
        print(f"[ERROR] Could not read {modality.upper()} file {file_path}: {e}")
        return None