import subprocess
import pandas as pd  # kept in case you later use it in log summaries
import os
import glob
from datetime import datetime
from tqdm import tqdm
from pathlib import Path


def main() -> None:
    """
    Launch all sweep CSV files matching the configured patterns as separate
    run_sweep.py processes and track them in a master log.
    """

    BASE_DIR = Path.home() / "Solar-Storage-Co-Optimization"
    INPUT_DIR = os.path.join(BASE_DIR, "Input_Files")
    CODE_DIR = os.path.join(BASE_DIR, "Code_Files")
    PY_DIR = os.path.join(BASE_DIR, "Python_Files")
    TXT_DIR = os.path.join(BASE_DIR, "Txt_files")
    LAUNCH_DIR = os.path.join(BASE_DIR, "Launch_files")
    OUT_DIR = os.path.join(BASE_DIR, "Outputs")

    os.makedirs(TXT_DIR, exist_ok=True)
    os.makedirs(OUT_DIR, exist_ok=True)

    # Prefer run_sweep.py in PY_DIR; fall back to CODE_DIR
    candidate_script = os.path.join(PY_DIR, "run_sweep.py")
    if not os.path.isfile(candidate_script):
        candidate_script = os.path.join(CODE_DIR, "run_sweep.py")
    sweep_script = candidate_script

    # Use a full timestamp for the master log (keeps logs unique)
    master_log_ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    master_log_path = os.path.join(TXT_DIR, f"master_log_{master_log_ts}.txt")

    # Use a shorter label (mm_dd) for run folders
    ts_label = datetime.now().strftime("%m_%d")

    # Patterns of sweep CSVs to launch
    patterns = ["test*.csv"]  # add e.g. "E*.csv" if desired
    sweep_files = []
    for pat in patterns:
        sweep_files.extend(glob.glob(os.path.join(LAUNCH_DIR, pat)))

    sweep_files = sorted(set(sweep_files), key=lambda p: (Path(p).stem.lower(), p))
    if not sweep_files:
        print("⚠️ No sweep CSV files found in Launch_files! Exiting.")
        raise SystemExit(1)

    print(f"\n🔍 Found {len(sweep_files)} sweep file(s):")
    for sf in sweep_files:
        print(f"  • {os.path.basename(sf)}")
    print("\n🚀 Launching all sweeps...\n")

    processes = []

    # Write launch info
    with open(master_log_path, "w", encoding="utf-8") as master_log:
        master_log.write(f"Master Sweep Launch Log - {datetime.now()}\n")
        master_log.write("=" * 80 + "\n\n")

        for sweep_file in sweep_files:
            stem = Path(sweep_file).stem
            parts = stem.split("_")  # e.g., "Base_case_launch"
            sweep_name = "_".join(parts[:3]) if len(parts) >= 2 else stem

            out_folder = os.path.join(OUT_DIR, f"Run_{sweep_name}__{ts_label}")
            os.makedirs(out_folder, exist_ok=True)

            run_id = f"run_{sweep_name}__{ts_label}"
            sheet_id = f"{sweep_name}__{ts_label}"

            command = [
                "python",
                sweep_script,
                "--sweep",
                sweep_file,
                "--sheet-id",
                sheet_id,
                "--run-id",
                run_id,
                "--output",
                out_folder,
            ]

            proc = subprocess.Popen(command, cwd=out_folder)
            processes.append((proc, sweep_name))

            launch_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            master_log.write(f"[LAUNCH] {sweep_name} at {launch_time}\n")
            master_log.write(f"Command: {' '.join(command)}\n")
            master_log.write(f"Output Folder: {out_folder}\n\n")

        master_log.write("=" * 80 + "\n")
        master_log.flush()

    # Track completion
    with open(master_log_path, "a", encoding="utf-8") as master_log:
        for proc, sweep_name in tqdm(processes, desc="Running Sweeps", ncols=90):
            return_code = proc.wait()
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            status = "✅ SUCCESS" if return_code == 0 else "❌ FAIL"
            master_log.write(f"[FINISH] {sweep_name} at {end_time} | Status: {status}\n")

        master_log.write("\nAll sweeps completed.\n")

    print(f"\n✅ All sweeps finished. See {master_log_path} for details.")


if __name__ == "__main__":
    main()

