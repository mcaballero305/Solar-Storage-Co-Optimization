# logging_utils.py
import logging
from amplpy import AMPL


def log_simulation_start(run_id: str, pv_type: str, bat_type: str):
    logging.info(f"[{run_id}] Running simulation for PV type: {pv_type}, Battery type: {bat_type}")


def log_simulation_params(ampl: AMPL, pv_type: str, bat_type: str):
    logging.debug("=== Simulation Debug Parameters ===")
    logging.debug("CRF_pv: %s", ampl.param["CRF_pv"].value())
    logging.debug("pv_cost[%s]: %s", pv_type, ampl.param["pv_cost"].get((pv_type,)))
    logging.debug("O_M[%s]: %s", pv_type, ampl.param["O_M"].get((pv_type,)))
    logging.debug("ac_e[%s]: %s", bat_type, ampl.param["ac_e"].get((bat_type,)))
    logging.debug("ac_p[%s]: %s", bat_type, ampl.param["ac_p"].get((bat_type,)))
    if "offset_price" in ampl.getParameters():
        logging.debug("offset_price: %s", ampl.param["offset_price"].value())



def log_sheet_name(run_id: str, sheet_name: str, generated: str):
    logging.debug(
        "[%s] Using sheet name: '%s' (generated: '%s')",
        run_id, sheet_name, generated
    )


def log_simulation_complete(run_id: str, config_id: str):
    logging.info(f"[{run_id}] Completed simulation for configuration: {config_id}")
