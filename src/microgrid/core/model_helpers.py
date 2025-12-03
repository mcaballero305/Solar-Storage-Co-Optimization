from __future__ import annotations

from pathlib import Path
from datetime import datetime
import math
import platform
import logging
import json
import os
import glob

import pandas as pd
import numpy as np
from amplpy import AMPL, add_to_path

logger = logging.getLogger(__name__)

# === AMPL path ===============================================================

_AMPL_ENV_VAR = "AMPL_DIR"
_AMPL_CONFIG_FILENAME = "ampl_config.json"


def _find_project_root(marker_files=("pyproject.toml", "setup.cfg", ".git")) -> Path:
    """
    Walk up from this file until we find a directory that looks like
    the project root (contains one of the marker files). If nothing is
    found, fall back to the parent directory of this file.
    """
    here = Path(__file__).resolve()
    for parent in [here] + list(here.parents):
        if any((parent / m).exists() for m in marker_files):
            return parent
    # Fallback: src/microgrid/core/ -> project root is three levels up
    return here.parents[3]


def _load_ampl_dir_from_config() -> Path | None:
    """
    Try to load AMPL directory from ampl_config.json at the project root.

    Expected JSON structure:
        { "ampl_dir": "C:/ampl" }
    """
    root = _find_project_root()
    cfg_path = root / _AMPL_CONFIG_FILENAME
    if not cfg_path.exists():
        return None

    try:
        data = json.loads(cfg_path.read_text())
        ampl_dir = data.get("ampl_dir")
        if ampl_dir:
            return Path(ampl_dir).expanduser()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Failed to parse %s: %s", cfg_path, exc)

    return None


def _candidate_ampl_dirs() -> list[Path]:
    """
    OS-specific fallback locations to check if neither the environment
    variable nor ampl_config.json are provided.
    """
    system = platform.system().lower()
    if "windows" in system:
        return [Path(r"C:\ampl"), Path(r"C:\AMPL")]
    # Linux / macOS
    return [Path("/opt/ampl"), Path("/usr/local/ampl"), Path("/usr/local/AMPL")]


def get_ampl_executable() -> str:
    """
    Resolve the full path to the AMPL executable.

    Resolution order:
        1. AMPL_DIR environment variable
        2. ampl_config.json at project root
        3. Common install directories (per OS)

    Raises:
        RuntimeError if no valid AMPL executable is found.
    """
    system = platform.system().lower()
    exe_name = "ampl.exe" if "windows" in system else "ampl"

    # 1) Environment variable
    env_dir = os.environ.get(_AMPL_ENV_VAR)
    if env_dir:
        ampl_dir = Path(env_dir).expanduser()
        ampl_path = ampl_dir / exe_name
        if ampl_path.is_file():
            logger.info("Using AMPL from %s (via %s)", ampl_path, _AMPL_ENV_VAR)
            return str(ampl_path)
        logger.warning(
            "%s is set to %s but %s was not found there.",
            _AMPL_ENV_VAR,
            ampl_dir,
            exe_name,
        )

    # 2) ampl_config.json at project root
    cfg_dir = _load_ampl_dir_from_config()
    if cfg_dir:
        ampl_path = cfg_dir / exe_name
        if ampl_path.is_file():
            logger.info("Using AMPL from %s (via ampl_config.json)", ampl_path)
            return str(ampl_path)
        logger.warning(
            "ampl_config.json specifies %s but %s was not found there.",
            cfg_dir,
            exe_name,
        )

    # 3) Common install locations
    for cand in _candidate_ampl_dirs():
        ampl_path = cand / exe_name
        if ampl_path.is_file():
            logger.info("Using AMPL from %s (auto-detected)", ampl_path)
            return str(ampl_path)

    # If we got here, nothing worked
    msg_lines = [
        "Could not locate the AMPL executable.",
        "",
        "Tried:",
        "  1) Environment variable AMPL_DIR",
        "  2) ampl_config.json at the project root",
        "  3) Common install locations (C:/ampl, /opt/ampl, /usr/local/ampl, ...)",
        "",
        "To fix this, either:",
        f"  - Set {_AMPL_ENV_VAR} to your AMPL directory, e.g.",
        "        set AMPL_DIR=C:\\ampl            (Windows, PowerShell)",
        "        export AMPL_DIR=/opt/ampl       (Linux/macOS, bash)",
        "    OR",
        f"  - Create {_AMPL_CONFIG_FILENAME} at the project root with:",
        '        { "ampl_dir": "C:/ampl" }',
    ]
    raise RuntimeError("\n".join(msg_lines))


# Global, so the rest of the module can just import/use it
AMPL_EXECUTABLE = get_ampl_executable()
AMPL_DIR = Path(AMPL_EXECUTABLE).parent

# === Repo + data paths =======================================================

THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[3]  # -> .../Solar-Storage-Co-Optimization

# For backward compatibility with older code that expected BASE_DIR:
BASE_DIR = REPO_ROOT

# microgrid package root
PKG_ROOT = REPO_ROOT / "src" / "microgrid"

# Inputs + model locations inside the package
INPUT_DIR = PKG_ROOT / "input_files"          # you must create this folder
CODE_DIR = PKG_ROOT / "solar_storage_model"   # contains solar_storage_model.mod

# Other legacy-style folders kept at repo root
PY_DIR = REPO_ROOT / "Python"      # if missing, we'll fall back to CODE_DIR
TXT_DIR = REPO_ROOT / "Txt_files"
OUT_DIR = REPO_ROOT / "Outputs"

OUT_DIR.mkdir(parents=True, exist_ok=True)
TXT_DIR.mkdir(parents=True, exist_ok=True)

# === Model & input tables ====================================================
# NOTE: Adjust file names here if your model/data/table filenames differ.
MODEL_PATH = CODE_DIR / "solar_storage_model.mod"
DATA_PATH = INPUT_DIR / "Hourly_parameter_data.csv"
PV_TABLE = INPUT_DIR / "bi_pv_table.csv"      # bi_pv_table, 2test_pv_table, Base_pv_table
BAT_TABLE = INPUT_DIR / "bat_tab_lion.csv"


# === Filename helpers for hourly CSVs ========================================

def _first_token_from_sweep(sweep_path: str) -> str:
    """
    Returns the first token (everything before the first underscore) from the sweep CSV filename stem.
    Example: 'Base_case_launch.csv' -> 'Base'
    """
    stem = Path(sweep_path).stem
    return stem.split("_", 1)[0] if "_" in stem else stem


def _fmt_itc(v):
    try:
        x = float(v)
    except Exception:
        return "0"
    if 0 <= x <= 1:
        x *= 100.0
    return str(int(round(x)))


def _fmt_area(v):
    try:
        return str(int(round(float(v))))
    except Exception:
        return "0"


def _fmt_money_or_price(v):
    try:
        x = float(v)
    except Exception:
        return "0"
    s = f"{x:.0f}" if float(x).is_integer() else f"{x:.2f}".rstrip("0").rstrip(".")
    return s if s else "0"


def make_hourly_csv_name(
    sweep_path: str,
    scalar_row: dict,
    overrides: dict | None = None,
) -> str:
    """
    Hourly CSV name spec:
      '<first_word_of_sweep>_<area>_<pvitc>_<batitc>_<offset>.csv'

    - area: comes from the LAUNCH CSV A_tot (if provided via overrides['A_tot']),
            otherwise falls back to scalar row labels.
    - pvitc/batitc: ITC as integer percent (e.g., 30, 10)
    - offset: numeric as concise string
    """
    first_token = _first_token_from_sweep(sweep_path)

    # Area must come from launch A_tot if available
    if overrides and "A_tot" in overrides and overrides["A_tot"] is not None:
        area_val = overrides["A_tot"]
    else:
        area_val = scalar_row.get("Max PV Array Area", 0)
    area_s = _fmt_area(area_val)

    pvitc_s = _fmt_itc(scalar_row.get("itc_PV", 0))
    batitc_s = _fmt_itc(scalar_row.get("itc_Bat", 0))

    # Offset: prefer explicit in overrides, fall back to scalar row label
    off = (overrides or {}).get(
        "offset_price",
        scalar_row.get("Offset Price ($/tCO2)", 0),
    )
    off_s = _fmt_money_or_price(off)

    return f"{first_token}_{area_s}_{pvitc_s}_{batitc_s}_{off_s}.csv"


# === Origin-policy helpers ====================================================

def _parse_list(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return set()
    return {s.strip() for s in str(val).split(";") if s.strip()}


def effective_pv_inputs_by_origin(pv_row, itc_pv, overrides):
    """
    Origin policy for PV:
      - if use_origin_policy==1:
          PV in pv_us_list -> ITC applies at scenario rate (itc_pv), no discount
          PV in pv_cn_list -> no ITC, apply cn_pv_discount_mult
        else: nominal (base, itc_pv)

    Returns (effective_base_cost, effective_itc).
    """
    base_nominal = float(pv_row["pv_cost"])
    itc_nominal = float(itc_pv)
    name = str(pv_row.get("PV_types", pv_row.get("PV_TYPE", "PV")))

    try:
        use_origin = bool(int(overrides.get("use_origin_policy", 0)))
    except Exception:
        use_origin = False

    if not use_origin:
        return base_nominal, itc_nominal

    us_list = _parse_list(overrides.get("pv_us_list"))
    cn_list = _parse_list(overrides.get("pv_cn_list"))
    try:
        cn_disc = float(overrides.get("cn_pv_discount_mult", 1.0) or 1.0)
    except Exception:
        cn_disc = 1.0

    if name in cn_list:
        return base_nominal * cn_disc, 0.0
    elif name in us_list:
        return base_nominal, itc_nominal
    else:
        return base_nominal, itc_nominal


def effective_battery_inputs_by_origin(bat_row, itc_bat, overrides):
    """
    Origin policy for Battery:
      - if use_origin_policy==1:
          BATTERY_TYPES in bat_us_list -> ITC applies at scenario rate (itc_bat), no discount
          BATTERY_TYPES in bat_cn_list -> no ITC, apply cn_bat_discount_mult_e and _p
        else: nominal (base_e, base_p, itc_bat)

    Returns (effective_cost_e, effective_cost_p, effective_itc_bat).
    """
    base_e = float(bat_row["B_cost_e"])
    base_p = float(bat_row["B_cost_p"])
    itc_nominal = float(itc_bat)
    name = str(bat_row.get("BATTERY_TYPES", bat_row.get("BAT_TYPE", "BAT")))

    try:
        use_origin = bool(int(overrides.get("use_origin_policy", 0)))
    except Exception:
        use_origin = False

    if not use_origin:
        return base_e, base_p, itc_nominal

    us_list = _parse_list(overrides.get("bat_us_list"))
    cn_list = _parse_list(overrides.get("bat_cn_list"))
    try:
        cn_disc_e = float(overrides.get("cn_bat_discount_mult_e", 1.0) or 1.0)
    except Exception:
        cn_disc_e = 1.0
    try:
        cn_disc_p = float(overrides.get("cn_bat_discount_mult_p", 1.0) or 1.0)
    except Exception:
        cn_disc_p = 1.0

    if name in cn_list:
        # China: discount, no ITC
        return base_e * cn_disc_e, base_p * cn_disc_p, 0.0
    elif name in us_list:
        # US: ITC applies, no discount
        return base_e, base_p, itc_nominal
    else:
        return base_e, base_p, itc_nominal


# === Path + AMPL helpers ======================================================

def get_paths():
    """
    Return a dict of key path locations as strings.
    """
    return dict(
        base_dir=str(BASE_DIR),
        input_dir=str(INPUT_DIR),
        code_dir=str(CODE_DIR),
        py_dir=str(PY_DIR if PY_DIR.is_dir() else CODE_DIR),
        txt_dir=str(TXT_DIR),
        outs_dir=str(OUT_DIR),
        model_path=str(MODEL_PATH),
        data_path=str(DATA_PATH),
        pv_table_path=str(PV_TABLE),
        bat_table_path=str(BAT_TABLE),
        ampl_path=str(AMPL_DIR),
        ampl_executable=str(AMPL_EXECUTABLE),
    )


def create_ampl():
    add_to_path(str(AMPL_DIR))
    return AMPL()


def reset_ampl_model(ampl, model_path: str):
    """Resets the AMPL model by reading in the given model file."""
    ampl.reset()
    ampl.read(model_path)


# === Time-of-use helpers ======================================================

def is_weekday(ts: pd.Timestamp) -> bool:
    return ts.weekday() < 5


def is_on_peak(ts: pd.Timestamp) -> bool:
    month = ts.month
    is_winter = month in [11, 12, 1, 2, 3]
    if is_weekday(ts):
        if is_winter:
            return (6 <= ts.hour < 10) or (18 <= ts.hour < 22)
        else:
            return 12 <= ts.hour < 21
    return False


# === Cost helpers =============================================================

def calculate_crf(rate: float, lifetime: int) -> float:
    return (rate * (1 + rate) ** lifetime) / ((1 + rate) ** lifetime - 1)


def calculate_replacement_years(lifetime: int, project_life: int) -> list[int]:
    return [t for t in range(lifetime, project_life, lifetime)]


def annualized_battery_cost(
    base_cost_e: float,
    base_cost_p: float,
    B_O_M: float,
    energy_life: int,
    power_life: int,
    project_life: int,
    discount_rate: float,
    replacement_fraction_e: float = 0.5,
    replacement_fraction_p: float = 0.5,
    itc_bat: float = 0.0,
    itc_pv: float = 0.0,  # unused, kept for signature compatibility
) -> tuple[float, float]:
    npv_e = base_cost_e + sum(
        (replacement_fraction_e * base_cost_e) / ((1 + discount_rate) ** t)
        for t in calculate_replacement_years(energy_life, project_life)
    )
    npv_p = base_cost_p + sum(
        (replacement_fraction_p * base_cost_p) / ((1 + discount_rate) ** t)
        for t in calculate_replacement_years(power_life, project_life)
    )
    crf = calculate_crf(discount_rate, project_life)
    ac_e = npv_e * crf * (1 - itc_bat) + B_O_M
    ac_p = npv_p * crf * (1 - itc_bat)
    return round(ac_e, 2), round(ac_p, 2)


def annualized_pv_cost(
    base_cost: float,
    o_m: float,
    project_life: int,
    discount_rate: float,
    itc_pv: float = 0.0,
) -> float:
    """Annualized PV cost ($/kW-yr), including ITC and O&M."""
    crf = calculate_crf(discount_rate, project_life)
    return round(base_cost * (1 - itc_pv) * crf + o_m, 2)


# === Misc helpers =============================================================

def safe_int(value, default=0):
    if pd.isna(value):
        return default
    try:
        return int(value)
    except Exception:
        return default


def append_scalar_to_sweep_summary(
    excel_filename: str,
    scalar_df: pd.DataFrame,
    sweep_filename: str,
):
    """
    Append scalar_df to a single sweep summary CSV that is named after the run folder.

    - Summary file: <run_folder_basename>_summary.csv
    - No per-run CSVs are emitted (prevents run_200_0_0_0.csv etc).
    """
    sweep_folder = os.path.dirname(excel_filename)        # e.g., ...\Outputs\Run_Base_case__11_11
    folder_base = os.path.basename(sweep_folder)          # e.g., Run_Base_case__11_11
    summary_path = os.path.join(sweep_folder, f"{folder_base}_summary.csv")

    # Order-stable append with header on first write
    if os.path.exists(summary_path):
        scalar_df.to_csv(summary_path, mode="a", header=False, index=False)
    else:
        scalar_df.to_csv(summary_path, mode="w", header=True, index=False)


def merge_sweep_summaries(base_folder: str, output_filename: str):
    """
    Merge all *__summary.csv files under base_folder into one CSV.
    """
    all_files = glob.glob(os.path.join(base_folder, "**", "*__summary.csv"), recursive=True)
    dfs = [pd.read_csv(f) for f in all_files if os.path.isfile(f)]
    if dfs:
        final_df = pd.concat(dfs, ignore_index=True)
        final_df.to_csv(os.path.join(base_folder, output_filename), index=False)


# === Monthly summary ==========================================================

def compute_monthly_summary(hourly_df: pd.DataFrame, data: pd.DataFrame, ampl) -> pd.DataFrame:
    data_hourly = data[["hour_id", "month", "onpeak"]].rename(columns={"hour_id": "Hour"})
    hourly_df["Hour"] = hourly_df["Hour"].astype(int)
    merged_df = pd.merge(hourly_df, data_hourly, on="Hour", how="left")

    demand_rate = ampl.param["demand_rate"].value()
    max_demand_rate = ampl.param["max_demand_rate"].value()
    monthly_charge = ampl.param["monthly_charge"].value()
    cost_sell = ampl.param["cost_sell"].value()
    offset_price = (
        ampl.param["offset_price"].value()
        if "offset_price" in ampl.getParameters()
        else 0.0
    )

    monthly_data = []
    for m in range(1, 13):
        month_df = merged_df[merged_df["month"] == m]
        if month_df.empty:
            continue

        on_df = month_df[month_df["onpeak"] == True]
        off_df = month_df[month_df["onpeak"] == False]

        off_energy = off_df["Grid Import"].sum()
        on_energy = on_df["Grid Import"].sum()
        off_cost = (off_df["Grid Import"] * off_df["Grid Price"]).sum()
        on_cost = (on_df["Grid Import"] * on_df["Grid Price"]).sum()

        onpeak_max = on_df["Grid Import"].max() if not on_df.empty else 0.0
        overall_max = month_df["Grid Import"].max()

        total_energy_cost = (
            (month_df["Grid Import"] * month_df["Grid Price"]).sum()
            - (month_df["Grid Export"] * cost_sell).sum()
        )
        demand_charge = onpeak_max * demand_rate
        max_demand_charge = overall_max * max_demand_rate
        total_demand_charges = demand_charge + max_demand_charge + monthly_charge
        total_monthly_cost = total_energy_cost + total_demand_charges

        gross_emissions = (
            (month_df["Grid Import"] * month_df["EF_grid"]).sum()
            if "EF_grid" in month_df
            else 0.0
        )

        abate_energy_kwh = 0.0
        if "Abatement_Energy_KWh" in month_df:
            abate_energy_kwh = month_df["Abatement_Energy_KWh"].sum()
        elif "Abatement_Energy_kWh" in month_df:
            abate_energy_kwh = month_df["Abatement_Energy_kWh"].sum()

        if "Abated_Emissions" in month_df:
            abated_emissions = month_df["Abated_Emissions"].sum()
        else:
            abated_emissions = 0.0

        net_emissions = gross_emissions - abated_emissions
        abatement_credit = offset_price * abated_emissions

        monthly_data.append(
            {
                "Month": m,
                "OffPeak_Energy": off_energy,
                "OffPeak_Cost": off_cost,
                "OnPeak_Energy": on_energy,
                "OnPeak_Cost": on_cost,
                "Total_Energy_Cost": total_energy_cost,
                "OnPeak_Max": onpeak_max,
                "Overall_Max": overall_max,
                "Demand_Charge": demand_charge,
                "Max_Demand_Charge": max_demand_charge,
                "Fixed_Charge": monthly_charge,
                "Total_Demand_Charges": total_demand_charges,
                "Total_Monthly_Cost": total_monthly_cost,
                "Gross_Emissions": gross_emissions,
                "Abatement_Energy_KWh": abate_energy_kwh,
                "Abated_Emissions": abated_emissions,
                "Net_Emissions": net_emissions,
                "Abatement_Credit_$": abatement_credit,
            }
        )

    monthly_df = pd.DataFrame(monthly_data)
    return monthly_df
