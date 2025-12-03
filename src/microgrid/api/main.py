from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from microgrid.core import model_helpers
from microgrid.core.model_helpers import create_ampl, reset_ampl_model
from microgrid.scripts.run_single_loop import run_single_pv


app = FastAPI()


# ---------------------------------------------------------------------------
# Helper: find project root (where pyproject.toml lives)
# ---------------------------------------------------------------------------

def find_project_root(start: Path) -> Path:
    """
    Walk up parent directories until we find pyproject.toml.
    This makes the app robust to where it's run from.
    """
    for parent in [start, *start.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: immediate parent if pyproject not found
    return start.parent


# ---------------------------------------------------------------------------
# Static frontend (simple HTML form)
# ---------------------------------------------------------------------------

THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = find_project_root(THIS_FILE)
FRONTEND_DIR = PROJECT_ROOT / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    """
    Serve the simple HTML frontend from frontend/index.html.
    """
    if not INDEX_HTML.exists():
        return JSONResponse(
            status_code=500,
            content={"error": f"index.html not found at {INDEX_HTML}"},
        )
    return FileResponse(INDEX_HTML)


# ---------------------------------------------------------------------------
# API: run a single configuration from uploaded CSV
# ---------------------------------------------------------------------------

@app.post("/run-single")
async def run_single(
    pv_type: str = Form(...),
    bat_type: str = Form(...),
    offset_price: float = Form(0.0),
    input_csv: UploadFile = File(...),
):
    """
    Run a single PV/BESS configuration using an uploaded CSV.

    - pv_type: name matching PV_types in the PV table (e.g., "Mono Si PERC")
    - bat_type: name matching BATTERY_TYPES in the battery table (e.g., "LFP_2h")
    - offset_price: $/tCO2 for abatement monetization
    - input_csv: user-uploaded CSV with the same structure as Hourly_parameter_data.csv
    """
    paths = model_helpers.get_paths()

    # Load PV & battery tables
    try:
        pv_tab = pd.read_csv(paths["pv_table_path"])
        bat_tab = pd.read_csv(paths["bat_table_path"])
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to load PV/Battery tables: {e}"},
        )

    # --- PV type lookup with helpful error ---
    pv_mask = pv_tab["PV_types"] == pv_type
    if not pv_mask.any():
        available_pv = ", ".join(sorted(pv_tab["PV_types"].astype(str).unique()))
        return JSONResponse(
            status_code=400,
            content={
                "error": f"PV type '{pv_type}' not found in PV table.",
                "available_pv_types": available_pv,
            },
        )
    pv_row = pv_tab.loc[pv_mask].iloc[0]

    # --- Battery type lookup with helpful error ---
    bat_mask = bat_tab["BATTERY_TYPES"] == bat_type
    if not bat_mask.any():
        available_bat = ", ".join(sorted(bat_tab["BATTERY_TYPES"].astype(str).unique()))
        return JSONResponse(
            status_code=400,
            content={
                "error": f"Battery type '{bat_type}' not found in battery table.",
                "available_battery_types": available_bat,
            },
        )
    bat_row = bat_tab.loc[bat_mask].iloc[0]

    # Prepare AMPL
    try:
        ampl = create_ampl()
        reset_ampl_model(ampl, paths["model_path"])
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to initialize AMPL: {e}"},
        )

    base_out_dir = Path(paths["outs_dir"])
    base_out_dir.mkdir(parents=True, exist_ok=True)

    # Temp working directory for this request
    with tempfile.TemporaryDirectory(dir=base_out_dir) as tmpdir_str:
        tmpdir = Path(tmpdir_str)

        # Save uploaded CSV into temp dir
        input_path = tmpdir / input_csv.filename
        try:
            with input_path.open("wb") as f:
                shutil.copyfileobj(input_csv.file, f)
        finally:
            input_csv.file.close()

        # Read uploaded data
        try:
            data = pd.read_csv(input_path)
        except Exception as e:
            return JSONResponse(
                status_code=400,
                content={"error": f"Failed to read uploaded CSV: {e}"},
            )

        excel_out = tmpdir / "single_run_result.xlsx"

        override_params = {"offset_price": offset_price}
        sizing_limits: dict = {}

        # Run the core engine
        scalar_df, hourly_df = run_single_pv(
            run_id=f"{pv_type}_{bat_type}",
            ampl=ampl,
            data=data,
            pv_data=pv_tab,
            pv_row=pv_row,
            bat_data=bat_tab,
            bat_row=bat_row,
            excel_filename=str(excel_out),
            override_params=override_params,
            sizing_limits=sizing_limits,
        )

        # If run_single_pv returned None, something went wrong
        if scalar_df is None or hourly_df is None:
            return JSONResponse(
                status_code=500,
                content={"error": "Simulation failed. See server logs for details."},
            )

        return FileResponse(
            path=excel_out,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="single_run_result.xlsx",
        )


