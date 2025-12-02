import os
import pandas as pd
import numpy as np
import argparse
import logging
from amplpy import AMPL, add_to_path
from datetime import timedelta
from microgrid.core import logging_utils, excel_utils
from microgrid.core.model_helpers import (
    get_paths,
    create_ampl,
    reset_ampl_model,
    safe_int,
    is_on_peak,
    append_scalar_to_sweep_summary,
    merge_sweep_summaries,
)
from microgrid.core.pv_sizing_limits import compute_pv_sizing_limits


from microgrid.scripts.run_single_loop import run_single_pv  # or: from .run_single_loop import run_single_pv


# === Parse Command-Line Arguments ===
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", type=str, required=True, help="Path to sweep CSV")
   # parser.add_argument("--override", type=str, required=True, help="Path to override CSV")
    parser.add_argument("--override", type=str, default="", help="Path to override CSV (optional)")

    parser.add_argument("--run-id", type=str, required=True, help="Unique ID for this sweep")
    parser.add_argument("--sheet-id", type=str, required=True)

    parser.add_argument("--output", type=str, required=True, help="Output folder")
    ###NEW STUFF TO SWEEP INSOLATION VALUES#####
    parser.add_argument(
    "--insolation-mult",
    type=float,
    default=1.0,
    help="Scale factor for insolation. Accepts 0.05 for +5%% or 1.05 for +5%%. "
         "Per-row sweep column 'insolation_mult' (if present) overrides this."
)

    return parser.parse_args()

def extract_value(param):
    return param.value() if hasattr(param, "value") else param
###NEW STUFF TO SWEEP INSOLATION VALUES#####
def _normalize_insolation_mult(x) -> float:
    """
    Accepts either % delta (e.g., 0.05, -0.05) or direct multiplier (e.g., 1.05).
    Returns a clean multiplier. Blank/NaN/invalid -> 1.0 (base).
    """
    import numpy as np

    # Treat None/blank strings/NaN as base
    if x is None:
        return 1.0
    if isinstance(x, str):
        s = x.strip()
        if not s:
            return 1.0
        # allow "5%" style too
        s = s.replace("%", "")
        try:
            v = float(s)
        except ValueError:
            return 1.0
    else:
        try:
            v = float(x)
        except Exception:
            return 1.0

    if np.isnan(v) or np.isinf(v):
        return 1.0

    # If magnitude < 1, interpret as ±% change; else treat as direct multiplier
    return (1.0 + v) if (-0.99 <= v <= 0.99) else v


def main():
    args = parse_args()
    run_id = args.run_id
    output_dir = args.output
    
    # === Load sweep and override parameters ===
    sweep_file_used = args.sweep
    sweep_base = os.path.splitext(os.path.basename(sweep_file_used))[0]
    
    # === Create output directory ===
    os.makedirs(output_dir, exist_ok=True)
    # === Setup logging ===
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(message)s',
        handlers=[
            logging.FileHandler(os.path.join(output_dir, "simulation.log")),
            logging.StreamHandler()
            ]
    )
    
    paths = get_paths()
    data_path = paths["data_path"]
    pv_table_path = paths["pv_table_path"]

    ampl = create_ampl()
    reset_ampl_model(ampl, paths["model_path"])
    
    sweep_df = pd.read_csv(args.sweep)
    print(f"🔍 Sweep file loaded: {len(sweep_df)} rows found.")

# Normalize/clean insolation_mult at source so blanks don't propagate as NaN
    if "insolation_mult" in sweep_df.columns:
        sweep_df["insolation_mult"] = sweep_df["insolation_mult"].apply(
            lambda x: None if (isinstance(x, str) and x.strip() == "") else x
        )


    override_params = {}
    if args.override:
        try:
            override_df = pd.read_csv(args.override)
            if not override_df.empty:
                override_params = override_df.to_dict(orient="records")[0]
        except Exception as e:
            logging.warning(f"Could not read override CSV '{args.override}': {e}")
    for idx, sweep_row in sweep_df.iterrows():
        full_params = {**override_params, **sweep_row.to_dict()}
        if ("offset_price" not in full_params) or pd.isna(full_params["offset_price"]):
            full_params["offset_price"] = 0.0
        # NEW STUFF FOR INSOLATION SWEEP Resolve insolation multiplier (row overrides CLI)
        row_ins_raw = full_params.get("insolation_mult", None)
        if (row_ins_raw is None) or (isinstance(row_ins_raw, float) and pd.isna(row_ins_raw)) \
        or (isinstance(row_ins_raw, str) and row_ins_raw.strip() == ""):
            row_ins_raw = getattr(args, "insolation_mult", 1.0)

        row_ins_mult = _normalize_insolation_mult(row_ins_raw)
        full_params["sweep_file"] = args.sweep
        logging.info(f"[{run_id}] Insolation multiplier (raw={row_ins_raw}) -> {row_ins_mult}")

            # --- clean A_tot from the sweep row (use LAUNCH value, not optimized area) ---
        def _safe_int(v, default=0):
            try:
                if v is None or (isinstance(v, float) and pd.isna(v)):
                    return default
                return int(round(float(v)))
            except Exception:
                return default

        launch_A_tot = _safe_int(full_params.get("A_tot"), 0)  # from the sweep CSV

    # build IDs and filename using sheet-id + LAUNCH A_tot
        run_id = f"{args.sheet_id}_A{launch_A_tot}"                # e.g., test_Base__11_12_A200
        excel_filename = os.path.join(output_dir, f"{run_id}.xlsx")

    # (optional but recommended) pass sweep file down so hourly CSV helper can name by sweep
    

     
        enable_sell = bool(safe_int(full_params.get("enable_sell", 1)))
        enforce_limit_flag = bool(safe_int(full_params.get("enforce_limit_flag", 0)))
        #enable_offsets = bool(model_helpers.safe_int(full_params.get("enable_offsets", 0)))
        #offset_price = float(full_params.get("offset_price", 0.0))
        #reward_factor = float(full_params.get("reward_factor", 0.0))
        print(f"🔧 [Main] Running row {idx} with full params: {full_params}")

        logging.info(f"[{run_id}] Full combined parameters: {full_params}")

        # === Prepare data ===
        data = pd.read_csv(paths["data_path"]).sort_values(["day", "hour"]).reset_index(drop=True)
        # Apply insolation scenario
        if "insolation" in data.columns:
            data["insolation"] = data["insolation"] * row_ins_mult
        else:
            logging.warning(f"[{run_id}] Column 'insolation' not found in data; skipping insolation scaling.")

        data["hour_id"] = data["hour"].astype(int)
        if 0 not in data["hour_id"].values:
            raise ValueError("❌ Hour 0 is missing from the dataset. Ensure your CSV includes it.")
        data["timestamp"] = data["hour_id"].apply(lambda h: pd.Timestamp("2023-01-01") + pd.Timedelta(hours=h - 1))
        data["onpeak"] = data["timestamp"].apply(is_on_peak)

        month_lengths = [31,28,31,30,31,30,31,31,30,31,30,31]
        data["month"] = 1
        cumulative = 0
        for m, days in enumerate(month_lengths, 1):
            mask = (data["day"] > cumulative) & (data["day"] <= cumulative + days)
            data.loc[mask, "month"] = m
            cumulative += days

        # === Load technology tables ===
        pv_data = pd.read_csv(paths["pv_table_path"])
        bat_data = pd.read_csv(paths["bat_table_path"])
    
        if ("offset_price" not in full_params) or pd.isna(full_params["offset_price"]):
            full_params["offset_price"] = 0.0

        # === Initialize AMPL ===

        # === Run all PV x Battery combinations ===

        # --- OPTIONAL TARGET FILTERS ---
        # Uncomment and set these to lock the sweep to one PV/Battery combo.
            # === Run Simulation ===
        for _, pv_row in pv_data.iterrows():
            if enforce_limit_flag:
                sizing_info = compute_pv_sizing_limits(
                    consumption_csv=data_path,
                    pv_table_csv=pv_table_path,
                    selected_module=pv_row["PV_types"],
                    safety_margin_percent=10
                )
                sizing_limits = {"Final Allowed System Size (kW)": sizing_info["Final Allowed System Size (kW)"]}
                print(f"✅ Computed sizing_info = {sizing_info}")
            else:
                sizing_limits = {"Final Allowed System Size (kW)": 1e6}
                print(f"✅ No sizing limit enforced. sizing_limits = {sizing_limits}")
                full_params.pop("A_tot", None)

                


            for _, bat_row in bat_data.iterrows():
                scalar_df, hourly_df = run_single_pv(
                    run_id,
                    ampl,
                    data,
                    pv_data,
                    pv_row,
                    bat_data,
                    bat_row,
                    excel_filename,
                    full_params,
                    sizing_limits
                )
                if scalar_df is not None:
                    append_scalar_to_sweep_summary(excel_filename, scalar_df,sweep_filename=args.sweep)

# === Hook for Running Script ===
if __name__ == "__main__":
    main()

