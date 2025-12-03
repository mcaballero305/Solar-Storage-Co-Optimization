from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import sys
import subprocess
import zipfile
import csv

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from microgrid.core import model_helpers


# -----------------------------------------------------------------------------
# FastAPI app + CORS
# -----------------------------------------------------------------------------

app = FastAPI(
    title="Solar + Storage Co-Optimization API",
    description=(
        "FastAPI front-end for the AMPL-based solar + storage MILP sweep. "
        "Provides endpoints for running sweeps via CSV upload or simple form inputs."
    ),
)

# Allow local dev frontends (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can tighten this later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------------------------------------------------------
# Simple index / health endpoints
# -----------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index():
    """
    Simple landing page; if you add a real frontend, you can update
    this to read and return frontend/index.html instead.
    """
    return """
    <!doctype html>
    <html lang="en">
    <head><meta charset="utf-8"><title>Solar–Storage MIP API</title></head>
    <body>
      <h1>Solar–Storage Co-Optimization API</h1>
      <p>
        Use <code>POST /run-sweep</code> to upload a sweep CSV, or
        <code>POST /run-sweep-form</code> to run a single scenario from form fields.
      </p>
    </body>
    </html>
    """


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# -----------------------------------------------------------------------------
# Shared helper: run sweep via subprocess and zip outputs
# -----------------------------------------------------------------------------

def _run_sweep_and_zip(
    run_id: str,
    sheet_id: str,
    insolation_mult: float,
    sweep_path: Path,
    override_path: Path | None = None,
):
    """
    Shared helper that invokes `python -m microgrid.scripts.run_sweep` and zips
    the resulting output directory.

    Returns either a FileResponse (ZIP) or a JSONResponse with error info.
    """
    paths = model_helpers.get_paths()
    base_out_dir = Path(paths["outs_dir"])
    base_out_dir.mkdir(parents=True, exist_ok=True)

    # Temp directory inside Outputs/ to keep things self-contained
    tmpdir_str = tempfile.mkdtemp(dir=base_out_dir)
    tmpdir = Path(tmpdir_str)

    out_dir = tmpdir / "sweep_outputs"
    out_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        sys.executable,
        "-m",
        "microgrid.scripts.run_sweep",
        "--sweep",
        str(sweep_path),
        "--run-id",
        run_id,
        "--sheet-id",
        sheet_id,
        "--output",
        str(out_dir),
        "--insolation-mult",
        str(insolation_mult),
    ]
    if override_path is not None:
        cmd.extend(["--override", str(override_path)])

    proc = subprocess.run(cmd, capture_output=True, text=True)

    if proc.returncode != 0:
        # Return detailed info to caller for debugging
        return JSONResponse(
            status_code=500,
            content={
                "error": "Sweep failed",
                "command": " ".join(cmd),
                "stdout": proc.stdout,
                "stderr": proc.stderr,
            },
        )

    # Zip all files inside out_dir
    zip_path = tmpdir / f"{run_id}_{sheet_id}_sweep_outputs.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in out_dir.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(out_dir))

    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=zip_path.name,
    )


# -----------------------------------------------------------------------------
# Existing CSV-upload API: /run-sweep
# -----------------------------------------------------------------------------

@app.post("/run-sweep")
async def run_sweep_endpoint(
    run_id: str = Form("web_sweep"),
    sheet_id: str = Form("WebSweep"),
    insolation_mult: float = Form(1.0),
    sweep_csv: UploadFile = File(...),
    override_csv: UploadFile | None = File(None),
):
    """
    Upload-based sweep endpoint.

    - Client uploads a full sweep CSV (multiple rows).
    - Optionally, an override CSV (first row applied to all).
    - Server saves CSVs to a temp directory, calls run_sweep via subprocess,
      then returns a ZIP of the Outputs.
    """
    paths = model_helpers.get_paths()
    base_out_dir = Path(paths["outs_dir"])
    base_out_dir.mkdir(parents=True, exist_ok=True)

    tmpdir_str = tempfile.mkdtemp(dir=base_out_dir)
    tmpdir = Path(tmpdir_str)

    try:
        # Save uploaded sweep CSV
        sweep_path = tmpdir / (sweep_csv.filename or "sweep.csv")
        try:
            with sweep_path.open("wb") as f:
                shutil.copyfileobj(sweep_csv.file, f)
        finally:
            sweep_csv.file.close()

        # Optional override CSV
        override_path: Path | None = None
        if override_csv is not None and override_csv.filename:
            override_path = tmpdir / override_csv.filename
            with override_path.open("wb") as f:
                shutil.copyfileobj(override_csv.file, f)
            override_csv.file.close()

        # Use shared helper to run and zip
        return _run_sweep_and_zip(
            run_id=run_id,
            sheet_id=sheet_id,
            insolation_mult=insolation_mult,
            sweep_path=sweep_path,
            override_path=override_path,
        )

    except Exception as e:
        # Fallback JSON error if something above blows up
        return JSONResponse(
            status_code=500,
            content={"error": f"Unexpected error in /run-sweep: {e}"},
        )


# -----------------------------------------------------------------------------
# New form-based API: /run-sweep-form
# -----------------------------------------------------------------------------

@app.post("/run-sweep-form")
async def run_sweep_form(
    # identifiers
    run_id: str = Form("web_form"),
    sheet_id: str = Form("WebForm"),
    # core scenario parameters
    A_tot: float = Form(...),
    itc_pv: float = Form(0.0),
    itc_bat: float = Form(0.0),
    offset_price: float = Form(0.0),
    enable_sell: int = Form(1),
    enforce_limit_flag: int = Form(0),
    insolation_mult: float = Form(1.0),
):
    """
    Simple scenario endpoint for a single row.

    Creates a one-row sweep CSV from scalar form parameters, then calls the
    same run_sweep helper used by /run-sweep and returns a ZIP of outputs.

    Exposed parameters are the ones actually consumed by run_sweep/run_single_loop:
    - A_tot
    - itc_pv
    - itc_bat
    - offset_price
    - enable_sell
    - enforce_limit_flag
    - insolation_mult
    """
    paths = model_helpers.get_paths()
    base_out_dir = Path(paths["outs_dir"])
    base_out_dir.mkdir(parents=True, exist_ok=True)

    tmpdir_str = tempfile.mkdtemp(dir=base_out_dir)
    tmpdir = Path(tmpdir_str)

    # Minimal column set consistent with your sweep & single-run code
    fieldnames = [
        "A_tot",
        "itc_pv",
        "itc_bat",
        "offset_price",
        "enable_sell",
        "enforce_limit_flag",
        "insolation_mult",
    ]

    sweep_path = tmpdir / "single_row_sweep.csv"

    try:
        # Write a single-row CSV
        with sweep_path.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(
                {
                    "A_tot": A_tot,
                    "itc_pv": itc_pv,
                    "itc_bat": itc_bat,
                    "offset_price": offset_price,
                    "enable_sell": enable_sell,
                    "enforce_limit_flag": enforce_limit_flag,
                    "insolation_mult": insolation_mult,
                }
            )

        # Reuse the same sweep runner; no override CSV for this simple UX
        return _run_sweep_and_zip(
            run_id=run_id,
            sheet_id=sheet_id,
            insolation_mult=insolation_mult,
            sweep_path=sweep_path,
            override_path=None,
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Unexpected error in /run-sweep-form: {e}"},
        )


