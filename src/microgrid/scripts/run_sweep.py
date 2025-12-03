from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import pandas as pd
import numpy as np

from amplpy import AMPL  # used via create_ampl()

from microgrid.core.model_helpers import (
    get_paths,
    create_ampl,
    reset_ampl_model,
    safe_int,
    is_on_peak,
    append_scalar_to_sweep_summary,
)
from microgrid.core.pv_sizing_limits import compute_pv_sizing_limits
from microgrid.scripts.run_single_loop import run_single_pv, normalize_hourly_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a sweep of PV/BESS configurations.")
    parser.add_argument(
        "--sweep",
        type=str,
        required=True,
        help="Path to sweep CSV.",
    )
    parser.add_argument(
        "--override",
        type=str,
        default="",
        help="Path to optional override CSV (first row applied to all sweep rows).",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="Base ID for this sweep run (used in logging).",
    )
    parser.add_argument(
        "--sheet-id",
        type=str,
        required=True,
        help="Base label used when naming per-run Excel files.",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="Output folder for Excel and log files.",
    )
    parser.add_argument(
        "--insolation-mult",
        type=float,
        default=1.0,
        help=(
            "Global scale factor for insolation (e.g., 0.9 for -10%%, 1.1 for +10%%). "
            "Per-row 'insolation_mult' in the sweep CSV overrides this."
        ),
    )
    return parser.parse_args()


def _normalize_insolation_mult(x) -> float:
    """
    Convert a value into a multiplicative insolation factor.

    Accepts:
      - None / blank -> 1.0
      - numeric like 0.95 or 1.05 (treated as multiplier directly)
      - numeric like 5, -5 (treated as +/- percent, i.e., 1 + x/100)
      - strings like "0.95", "1.05", "5%", "-5%"

    Returns a multiplier (e.g. 1.05 means +5 percent).
    """
    if x is None:
        return 1.0

    if isinstance(x, str):
        s = x.strip()
        if not s:
            return 1.0
        if s.endswith("%"):
            try:
                pct = float(s[:-1])
                return 1.0 + pct / 100.0
            except Exception:
                return 1.0
        try:
            val = float(s)
        except Exception:
            return 1.0
    else:
        try:
            val = float(x)
        except Exception:
            return 1.0

    # Interpret values near 1 as direct multipliers, larger values as percents
    if -2.0 <= val <= 2.0:
        return val
    return 1.0 + val / 100.0


def _safe_int_local(v, default=0) -> int:
    try:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        return int(round(float(v)))
    except Exception:
        return default


def main() -> None:
    args = parse_args()

    run_id_base = args.run_id
    output_dir = args.output
    os.makedirs(output_dir, exist_ok=True)

    # Set up logging to console and file (ASCII messages only).
    sweep_base = os.path.splitext(os.path.basename(args.sweep))[0]
    log_path = os.path.join(output_dir, f"{run_id_base}__{sweep_base}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_path, mode="w", encoding="utf-8"),
        ],
    )

    logging.info("[%s] Starting sweep.", run_id_base)
    logging.info("[%s] Sweep file: %s", run_id_base, args.sweep)
    if args.override:
        logging.info("[%s] Override CSV: %s", run_id_base, args.override)

    # Core paths
    paths = get_paths()
    data_path = paths["data_path"]
    pv_table_path = paths["pv_table_path"]
    bat_table_path = paths["bat_table_path"]

    # AMPL model
    ampl = create_ampl()
    reset_ampl_model(ampl, paths["model_path"])

    # Load sweep CSV
    sweep_df = pd.read_csv(args.sweep)
    logging.info("[%s] Sweep file loaded: %d rows found.", run_id_base, len(sweep_df))

    # Clean up insolation_mult so blanks become None
    if "insolation_mult" in sweep_df.columns:
        sweep_df["insolation_mult"] = sweep_df["insolation_mult"].apply(
            lambda x: None if (isinstance(x, str) and x.strip() == "") else x
        )

    # Load optional override parameters
    override_params: dict = {}
    if args.override:
        try:
            override_df = pd.read_csv(args.override)
            if not override_df.empty:
                override_params = override_df.to_dict(orient="records")[0]
                logging.info("[%s] Loaded override params: %s", run_id_base, override_params)
        except Exception as e:
            logging.warning(
                "[%s] Could not read override CSV '%s': %s",
                run_id_base,
                args.override,
                e,
            )

    # Iterate each row in sweep CSV
    for idx, sweep_row in sweep_df.iterrows():
        full_params = {**override_params, **sweep_row.to_dict()}

        # Ensure offset_price is present
        if ("offset_price" not in full_params) or pd.isna(full_params["offset_price"]):
            full_params["offset_price"] = 0.0

        # Resolve insolation multiplier: per-row overrides CLI value
        row_ins_raw = full_params.get("insolation_mult", None)
        if (
            row_ins_raw is None
            or (isinstance(row_ins_raw, float) and pd.isna(row_ins_raw))
            or (isinstance(row_ins_raw, str) and row_ins_raw.strip() == "")
        ):
            row_ins_raw = getattr(args, "insolation_mult", 1.0)

        row_ins_mult = _normalize_insolation_mult(row_ins_raw)
        full_params["insolation_mult"] = row_ins_mult
        full_params["sweep_file"] = args.sweep

        # Enable/disable flags
        enable_sell = bool(safe_int(full_params.get("enable_sell", 1)))
        enforce_limit_flag = bool(safe_int(full_params.get("enforce_limit_flag", 0)))
        full_params["enable_sell"] = int(enable_sell)
        full_params["enforce_limit_flag"] = int(enforce_limit_flag)

        # Clean A_tot from the sweep row (LAUNCH value, not optimized area)
        launch_A_tot = _safe_int_local(full_params.get("A_tot"), 0)

        # Build IDs / filenames using sheet-id + LAUNCH A_tot
        row_run_id = f"{args.sheet_id}_A{launch_A_tot}"
        excel_filename = os.path.join(output_dir, f"{row_run_id}.xlsx")

        logging.info(
            "[%s] Row %d: A_tot=%d, insolation_mult(raw=%s) -> %f, "
            "enforce_limit=%s, enable_sell=%s",
            run_id_base,
            idx,
            launch_A_tot,
            str(row_ins_raw),
            row_ins_mult,
            enforce_limit_flag,
            enable_sell,
        )
        logging.info("[%s] Full combined parameters: %s", run_id_base, full_params)

        # === Prepare base hourly data ===
        data = pd.read_csv(data_path).sort_values(["day", "hour"]).reset_index(drop=True)

        # Apply insolation scaling if column exists
        if "insolation" in data.columns:
            data["insolation"] = data["insolation"] * row_ins_mult
        else:
            logging.warning(
                "[%s] Row %d: Column 'insolation' not in data; skipping insolation scaling.",
                run_id_base,
                idx,
            )

        # Derive hour_id, timestamp, onpeak, and month
        if "hour_id" not in data.columns:
            if "hour" in data.columns:
                data["hour_id"] = data["hour"].astype(int)
            else:
                data.insert(0, "hour_id", range(len(data)))
        else:
            data["hour_id"] = data["hour_id"].astype(int)

        if 0 not in data["hour_id"].values:
            raise ValueError(
                "[%s] Hour 0 is missing from the dataset. Ensure your CSV includes it."
                % row_run_id
            )

        data["timestamp"] = data["hour_id"].apply(
            lambda h: pd.Timestamp("2023-01-01") + pd.Timedelta(hours=h - 1)
        )
        data["onpeak"] = data["timestamp"].apply(is_on_peak)

        # Build a month index from "day" if present
        if "day" in data.columns:
            month_lengths = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            data["month"] = 1
            cumulative = 0
            for m, days in enumerate(month_lengths, 1):
                mask = (data["day"] > cumulative) & (data["day"] <= cumulative + days)
                data.loc[mask, "month"] = m
                cumulative += days

        # Normalize structure for downstream code (guarantee 'hour_id')
        data = normalize_hourly_data(data)

        # === Load technology tables ===
        pv_data = pd.read_csv(pv_table_path)
        bat_data = pd.read_csv(bat_table_path)

        # === Sizing limits ===
        if enforce_limit_flag:
            sizing_info = compute_pv_sizing_limits(
                consumption_csv=data_path,
                pv_table_csv=pv_table_path,
                selected_module=pv_data["PV_types"].iloc[0],
                safety_margin_percent=10,
            )
            sizing_limits = {
                "Final Allowed System Size (kW)": sizing_info["Final Allowed System Size (kW)"]
            }
            logging.info("[%s] Row %d sizing_info: %s", run_id_base, idx, sizing_info)
        else:
            sizing_limits = {"Final Allowed System Size (kW)": 1e6}
            logging.info(
                "[%s] Row %d: No sizing limit enforced. sizing_limits=%s",
                run_id_base,
                idx,
                sizing_limits,
            )
            full_params.pop("A_tot", None)

        # === Run all PV x Battery combinations for this row ===
        for _, pv_row in pv_data.iterrows():
            for _, bat_row in bat_data.iterrows():
                scalar_df, hourly_df = run_single_pv(
                    run_id=row_run_id,
                    ampl=ampl,
                    data=data,
                    pv_data=pv_data,
                    pv_row=pv_row,
                    bat_data=bat_data,
                    bat_row=bat_row,
                    excel_filename=excel_filename,
                    override_params=full_params,
                    sizing_limits=sizing_limits,
                )
                if scalar_df is not None:
                    append_scalar_to_sweep_summary(
                        excel_filename,
                        scalar_df,
                        sweep_filename=args.sweep,
                    )

    logging.info("[%s] Sweep complete.", run_id_base)


if __name__ == "__main__":
    main()
