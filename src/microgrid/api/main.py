from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import sys
import subprocess
import zipfile

from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from microgrid.core import model_helpers


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
# Static frontend (simple HTML page)
# ---------------------------------------------------------------------------

THIS_FILE = Path(__file__).resolve()
PROJECT_ROOT = find_project_root(THIS_FILE)
FRONTEND_DIR = PROJECT_ROOT / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    """
    Serve the sweep-only HTML frontend from frontend/index.html.
    """
    if not INDEX_HTML.exists():
        return JSONResponse(
            status_code=500,
            content={"error": f"index.html not found at {INDEX_HTML}"},
        )
    return FileResponse(INDEX_HTML)


# ---------------------------------------------------------------------------
# API: run a sweep via microgrid.scripts.run_sweep
# ---------------------------------------------------------------------------

@app.post("/run-sweep")
async def run_sweep_endpoint(
    run_id: str = Form("web_sweep"),
    sheet_id: str = Form("WebSweep"),
    insolation_mult: float = Form(1.0),
    sweep_csv: UploadFile = File(...),
    override_csv: UploadFile | None = File(None),
):
    """
    Run a full sweep using microgrid.scripts.run_sweep by shelling out:

        python -m microgrid.scripts.run_sweep ...

    Returns a ZIP file of all generated outputs.
    """
    paths = model_helpers.get_paths()
    base_out_dir = Path(paths["outs_dir"])
    base_out_dir.mkdir(parents=True, exist_ok=True)

    # IMPORTANT: use mkdtemp (no context manager) so the directory is not deleted
    tmpdir_str = tempfile.mkdtemp(dir=base_out_dir)
    tmpdir = Path(tmpdir_str)

    try:
        # Save sweep CSV
        sweep_path = tmpdir / sweep_csv.filename
        try:
            with sweep_path.open("wb") as f:
                shutil.copyfileobj(sweep_csv.file, f)
        finally:
            sweep_csv.file.close()

        # Optional override CSV
        override_path = None
        if override_csv is not None and override_csv.filename:
            override_path = tmpdir / override_csv.filename
            with override_path.open("wb") as f:
                shutil.copyfileobj(override_csv.file, f)
            override_csv.file.close()

        # Output directory for the sweep script
        out_dir = tmpdir / "sweep_outputs"
        out_dir.mkdir(parents=True, exist_ok=True)

        # Build the command
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

        # Run the sweep as a subprocess
        proc = subprocess.run(cmd, capture_output=True, text=True)

        if proc.returncode != 0:
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Sweep failed",
                    "command": " ".join(cmd),
                    "stdout": proc.stdout,
                    "stderr": proc.stderr,
                },
            )

        # Zip the output directory
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

    except Exception as e:
        # Fallback JSON error if something above blows up
        return JSONResponse(
            status_code=500,
            content={"error": f"Unexpected error in /run-sweep: {e}"},
        )

