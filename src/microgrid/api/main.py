from pathlib import Path
import tempfile
import shutil

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse

from microgrid.core import model_helpers
from microgrid.scripts.run_single_loop import run_single_pv  # you'll expose a function

app = FastAPI()

@app.post("/run-single")
async def run_single(
    pv_type: str = Form(...),
    bat_type: str = Form(...),
    offset_price: float = Form(0.0),
    input_csv: UploadFile = File(...),
):
    """
    Run a single PV/BESS configuration with a user-uploaded CSV.
    Returns the generated Excel file.
    """
    paths = model_helpers.get_paths()
    base_dir = Path(paths["base_dir"])

    # Temp working directory for this request
    with tempfile.TemporaryDirectory(dir=base_dir / "Outputs") as tmpdir:
        tmpdir = Path(tmpdir)

        # Save uploaded CSV into temp dir
        input_path = tmpdir / input_csv.filename
        with input_path.open("wb") as f:
            shutil.copyfileobj(input_csv.file, f)

        # Load your â€œstandardâ€ input tables
        import pandas as pd

        data = pd.read_csv(input_path)
        pv_tab = pd.read_csv(paths["pv_table_path"])
        bat_tab = pd.read_csv(paths["bat_table_path"])

        pv_row = pv_tab.loc[pv_tab["PV_types"] == pv_type].iloc[0]
        bat_row = bat_tab.loc[bat_tab["BATTERY_TYPES"] == bat_type].iloc[0]

        # Prepare AMPL
        from microgrid.core.model_helpers import create_ampl, reset_ampl_model

        ampl = create_ampl()
        reset_ampl_model(ampl, paths["model_path"])

        excel_out = tmpdir / "single_run_result.xlsx"

        override_params = {"offset_price": offset_price}
        sizing_limits = {}

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

        # Return the Excel file as a download
        return FileResponse(
            path=excel_out,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="single_run_result.xlsx",
        )
PS C:\Users\yonoy\abba\src\microgrid> cat .\api\main.py
from pathlib import Path
import tempfile
import shutil

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse

from microgrid.core import model_helpers
from microgrid.scripts.run_single_loop import run_single_pv  # you'll expose a function

app = FastAPI()

@app.post("/run-single")
async def run_single(
    pv_type: str = Form(...),
    bat_type: str = Form(...),
    offset_price: float = Form(0.0),
    input_csv: UploadFile = File(...),
):
    """
    Run a single PV/BESS configuration with a user-uploaded CSV.
    Returns the generated Excel file.
    """
    paths = model_helpers.get_paths()
    base_dir = Path(paths["base_dir"])

    # Temp working directory for this request
    with tempfile.TemporaryDirectory(dir=base_dir / "Outputs") as tmpdir:
        tmpdir = Path(tmpdir)

        # Save uploaded CSV into temp dir
        input_path = tmpdir / input_csv.filename
        with input_path.open("wb") as f:
            shutil.copyfileobj(input_csv.file, f)

        # Load your â€œstandardâ€ input tables
        import pandas as pd

        data = pd.read_csv(input_path)
        pv_tab = pd.read_csv(paths["pv_table_path"])
        bat_tab = pd.read_csv(paths["bat_table_path"])

        pv_row = pv_tab.loc[pv_tab["PV_types"] == pv_type].iloc[0]
        bat_row = bat_tab.loc[bat_tab["BATTERY_TYPES"] == bat_type].iloc[0]

        # Prepare AMPL
        from microgrid.core.model_helpers import create_ampl, reset_ampl_model

        ampl = create_ampl()
        reset_ampl_model(ampl, paths["model_path"])

        excel_out = tmpdir / "single_run_result.xlsx"

        override_params = {"offset_price": offset_price}
        sizing_limits = {}

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

        # Return the Excel file as a download
        return FileResponse(
            path=excel_out,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            filename="single_run_result.xlsx",
        )