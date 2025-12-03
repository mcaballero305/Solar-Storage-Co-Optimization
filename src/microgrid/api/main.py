
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from microgrid.core import model_helpers
from microgrid.core.model_helpers import create_ampl, reset_ampl_model
from microgrid.scripts.run_single_loop import run_single_pv

app = FastAPI()

# ---------------------------------------------------------------------------
# Static frontend (simple HTML form)
# ---------------------------------------------------------------------------

# This file is src/microgrid/api/main.py
THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = THIS_FILE.parents[4]  # .../Solar-Storage-Co-Optimization
FRONTEND_DIR = PROJECT_ROOT / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"

# Allow browser access (adjust origins as needed later)
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
    Serve the simple HTML frontend from /frontend/index.html.
    """
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

    - pv_type: string matching PV_types in your PV table (e.g., "Mono Si PERC")
    - bat_type: string matching BATTERY_TYPES in your battery table (e.g., "LFP_2h")
    - offset_price: $/tCO2 for abatement monetization
    - input_csv: user-uploaded CSV with the same structure as Hourly_parameter_data.csv
    """
    paths = model_helpers.get_paths()

    # Prepare AMPL and data tables
    ampl = create_ampl()
    reset_ampl_model(ampl, paths["model_path"])

    # Load PV and battery tables using your existing paths
    pv_tab = pd.read_csv(paths["pv_table_path"])
    bat_tab = pd.read_csv(paths["bat_table_path"])

    # Resolve the selected PV / battery rows
    pv_row = pv_tab.loc[pv_tab["PV_types"] == pv_type].iloc[0]
    bat_row = bat_tab.loc[bat_tab["BATTERY_TYPES"] == bat_type].iloc[0]

    # Temp working directory for this request
    base_out_dir = Path(paths["outs_dir"])
    base_out_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=base_out_dir) as tmpdir_str:
        tmpdir = Path(tmpdir_str)

        # Save uploaded CSV into temp dir
        input_path = tmpdir / input_csv.filename
        with input_path.open("wb") as f:
            shutil.copyfileobj(input_csv.file, f)

        # Read the uploaded CSV as the "data" table
        data = pd.read_csv(input_path)

        excel_out = tmpdir / "single_run_result.xlsx"

        override_params = {"offset_price": offset_price}
        sizing_limits: dict = {}

        # Call your existing engine
        run_single_pv(
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

        return FileResponse(
            path=excel_out,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="single_run_result.xlsx",
        )
