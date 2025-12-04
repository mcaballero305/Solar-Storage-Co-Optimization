from __future__ import annotations

import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse

from microgrid.scripts.run_sweep import run_sweep_main
from microgrid.core import model_helpers
from microgrid.core.model_helpers import OUT_DIR

app = FastAPI(
    title="Solar-Storage Co-Optimization API",
    description="Upload a sweep CSV, run the AMPL-based MILP, and download results as a ZIP.",
    version="0.1.0",
)

# Paths
THIS_FILE = Path(__file__).resolve()
REPO_ROOT = THIS_FILE.parents[4]  # .../Solar-Storage-Co-Optimization
FRONTEND_DIR = REPO_ROOT / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------

def _make_run_id(user_run_id: Optional[str]) -> str:
    """Generate a safe run_id if the user didn't provide one."""
    if user_run_id:
        return user_run_id.replace(" ", "_")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"api_run_{ts}"


def _make_output_dir(run_id: str) -> Path:
    """
    Create an output directory under Outputs/api_runs/<run_id>.
    Uses the OUT_DIR defined in model_helpers (repo_root/Outputs).
    """
    base = OUT_DIR / "api_runs" / run_id
    base.mkdir(parents=True, exist_ok=True)
    return base


def _save_upload(file: UploadFile, dest_dir: Path) -> Path:
    """Save the uploaded file to dest_dir and return its path."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")

    dest_path = dest_dir / file.filename
    with dest_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    return dest_path


def _zip_output_dir(output_dir: Path, run_id: str) -> Path:
    """
    Zip the contents of output_dir into Outputs/<run_id>_results.zip
    and return the path to the ZIP.
    """
    zip_base = OUT_DIR / f"{run_id}_results"
    # make_archive adds .zip automatically
    zip_path_str = shutil.make_archive(
        base_name=str(zip_base),
        format="zip",
        root_dir=str(output_dir),
    )
    return Path(zip_path_str)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def serve_index() -> HTMLResponse:
    """
    Serve the simple HTML front-end for uploading a sweep CSV.
    """
    if INDEX_HTML.exists():
        return HTMLResponse(INDEX_HTML.read_text(encoding="utf-8"))
    # Fallback if the file is missing
    return HTMLResponse(
        "<h1>Solar-Storage Co-Optimization</h1>"
        "<p>frontend/index.html not found. Please add it to use the web UI.</p>",
        status_code=200,
    )


@app.post("/run-sweep")
async def run_sweep_endpoint(
    sweep_file: UploadFile = File(..., description="Sweep CSV (e.g., sweep_1_itc_area.csv)"),
    run_id: Optional[str] = Form(None),
    sheet_id: Optional[str] = Form(None),
    insolation_mult: float = Form(1.0),
):
    """
    Upload a sweep CSV, run the MILP, and download a ZIP of the results.
    """
    # Basic validation
    if not sweep_file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are accepted.")

    # Construct run identifiers and paths
    run_id_final = _make_run_id(run_id)
    sheet_id_final = sheet_id or run_id_final
    output_dir = _make_output_dir(run_id_final)

    # Save uploaded file into the output directory
    saved_sweep_path = _save_upload(sweep_file, output_dir)

    # Run the sweep via the same backend as the CLI
    try:
        run_sweep_main(
            sweep_csv=str(saved_sweep_path),
            run_id=run_id_final,
            sheet_id=sheet_id_final,
            output_dir=str(output_dir),
            insolation_mult=insolation_mult,
        )
    except Exception as exc:
        # Surface a readable error in the browser
        raise HTTPException(
            status_code=500,
            detail=f"Error running sweep: {exc}",
        ) from exc

    # Zip the results and return as download
    zip_path = _zip_output_dir(output_dir, run_id_final)

    if not zip_path.is_file():
        raise HTTPException(
            status_code=500,
            detail="Run completed but results ZIP could not be created.",
        )

    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=zip_path.name,
    )


@app.get("/health", response_class=PlainTextResponse)
async def health() -> str:
    """
    Simple health check endpoint.
    """
    return "ok"


# Optional: expose paths for debugging (not strictly required)
@app.get("/debug/paths", response_class=PlainTextResponse)
async def debug_paths() -> str:
    paths = model_helpers.get_paths()
    lines = [
        f"BASE_DIR:   {paths['base_dir']}",
        f"INPUT_DIR:  {paths['input_dir']}",
        f"CODE_DIR:   {paths['code_dir']}",
        f"OUTS_DIR:   {paths['outs_dir']}",
        f"AMPL_DIR:   {paths['ampl_path']}",
        f"AMPL_EXE:   {paths['ampl_executable']}",
    ]
    return "\n".join(lines)
