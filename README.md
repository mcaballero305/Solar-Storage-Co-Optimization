# Solar-Storage Co-Optimization: MILP-Based Solar + Storage Co-Optimization Model

Extension package built around an AMPL mixed-integer linear program (MILP) with a Python front-end, enabling solar PV + battery storage co-optimization for a commercial & industrial (C&I) facility under realistic tariff and policy conditions.

The model is designed for:

- PV + battery sizing and dispatch optimization
- Policy scenario analysis (ITC, emissions credits)
- Tariff-structured economic evaluation

## Features

- **System Optimization**  
  - Co-optimizes PV array area (subject to an interconnection cap) and BESS energy/power.  
  - Selects among PV module types (e.g., mono-Si PERC, mono-bifacial, CdTe) and battery chemistries (e.g., Li-ion LFP) via discrete decision variables.

- **Tariff-Driven Economic Analysis**  
  - Implements utility rate structures (e.g., energy and demand charges) for a C&I manufacturing facility served under FPL’s GSLDT-1 tariff.  
  - Produces hourly and monthly cost breakdowns and scalar economic outputs.

- **Scenario and Policy Sweeps**  
  - Supports parametric sweeps over:
    - PV ITC (0–50%)  
    - Battery ITC (0–50%)  
    - PV array area (up to an interconnection limit)  
    - Emissions offset price (e.g., \$0–0.03/tCO₂)  
  - Origin-based policy toggles (e.g., differential ITC/costs for certain PV or battery origins).

- **Structured Outputs**  
  - Hourly (`H_*`) sheets: dispatch, state of charge, power flows, and hourly costs.  
  - Monthly (`M_*`) sheets: tariff-based cost components and summary metrics.  
  - Configuration-level scalar summaries and merged sweep summary CSVs/Excel files.

- **Batch Sweep Processing**  
  - Sweeps defined via CSV (`Launch_Files/*.csv`).  
  - Optional driver to run multiple sweep files and consolidate logs.

- **Optional Web API**  
  - FastAPI-based interface: upload a sweep CSV and download a ZIP of results (run locally).  

---

## Installation

    # Clone Solar-Storage Co-Optimization repository
    git clone https://github.com/mcaballero305/Solar-Storage-Co-Optimization.git
    cd Solar-Storage-Co-Optimization

Or download the repository as a ZIP directly from the GitHub page and unzip it locally.

### Required Dependencies

1. **Python Version**

   - Recommended: Python **3.10** or **3.11**.

2. **AMPL (Optimization Engine)**

   - A local AMPL installation is required (AMPL Community Edition is sufficient).  
   - Download AMPL CE and obtain a free license from the AMPL website.  
   - Install AMPL in a directory you control (for example):  
     - Windows: `C:\ampl\`  
     - Linux/macOS: `/opt/ampl/`  

3. **Python Packages (from `requirements.txt`)**

   Create and activate a virtual environment, then install the package in editable mode:

   **Windows (PowerShell)**

       python -m venv .venv
       .\.venv\Scripts\Activate.ps1
       python -m pip install --upgrade pip setuptools wheel
       python -m pip install -e .

   **Linux/macOS (bash)**

       python3 -m venv .venv
       source .venv/bin/activate
       python -m pip install --upgrade pip setuptools wheel
       python -m pip install -e .

4. **AMPL Path Configuration**

   The recommended way to tell the code where AMPL is installed is:

   1. **Environment variable (preferred)**  
      Set `AMPL_DIR` to the directory that contains the `ampl` / `ampl.exe` binary.

      - Windows (PowerShell):  
            setx AMPL_DIR "C:\ampl"
      - Linux/macOS (bash):  
            export AMPL_DIR=/opt/ampl

   2. **Config file (alternative)**  
      Create a file named `ampl_config.json` in the project root (same folder as `pyproject.toml`) with:

          { "ampl_dir": "C:/ampl" }

      Use forward slashes or escaped backslashes on Windows.

   At runtime, the helper `get_ampl_executable()` in `src/microgrid/core/model_helpers.py`:

   - First checks `AMPL_DIR`  
   - Then checks `ampl_config.json`  
   - Finally, tries common install paths (`C:\ampl`, `/opt/ampl`, `/usr/local/ampl`, etc.)

   If none of these work, it raises a clear error explaining how to set `AMPL_DIR` or create `ampl_config.json`.

---

## Documentation

This README is the primary documentation for the repository. For additional context on the modeling assumptions, objective function, and scenario design, see the associated dissertation text (not included here) which this codebase supports.

Inline comments in:

- `src/microgrid/core/`  
- `src/microgrid/scripts/`  

provide more detail on specific helper functions and workflow steps.

---

## Quick Start

### CLI Quick Start

After installing the package and configuring the AMPL path:

    microgrid-sweep-run \
      --sweep Launch_Files/sweep_1_itc_area.csv \
      --run-id demo_sweep \
      --sheet-id Demo \
      --output Outputs/Demo_Run \
      --insolation-mult 1.0

This will:

- Read the sweep configuration from `Launch_Files/sweep_1_itc_area.csv`.  
- For each row (scenario) in the sweep file, call the AMPL backend to solve the MILP.  
- Write Excel and CSV outputs into `Outputs/Demo_Run/` with one or more workbooks and summary files.

If the command completes without error and you see new files in `Outputs/Demo_Run/`, your environment is correctly configured.

### Python API Quick Start

You can also invoke the sweep runner directly from Python instead of using the CLI:

    from microgrid.scripts.run_sweep import run_sweep_main

    result_paths = run_sweep_main(
        sweep_csv="Launch_Files/sweep_1_itc_area.csv",
        run_id="demo_sweep",
        sheet_id="Demo",
        output_dir="Outputs/Demo_Run",
        insolation_mult=1.0,
    )

    print("Generated result files:")
    for p in result_paths:
        print(p)

This mirrors the CLI behavior but returns a list of created files (paths) for further processing in Python.

---

## Required Files

The model expects several input CSV files, organized as follows:

1. **Hourly Parameter Data**

   - Path: `Input_Files/Hourly_parameter_data.csv`  
   - Contains 8,760 rows (one per hour) for:
     - Facility load  
     - Solar resource (e.g., plane-of-array irradiance or related fields used by the model)  
     - Tariff components (e.g., energy price, demand periods)  
     - Emissions factors (if applicable)  

2. **PV Technology Table**

   - Path: `Input_Files/bi_pv_table.csv`  
   - Contains data for available PV module types:
     - Name/ID of PV technology  
     - Cost and efficiency parameters  
     - Origin flags (for applying ITC/cost adjustments)  
     - Any other PV parameters used by the AMPL model  

3. **Battery Technology Table**

   - Path: `Input_Files/bat_tab_lion.csv`  
   - Contains data for available battery technologies:
     - Name/ID of battery chemistry  
     - Capital cost (energy and power components)  
     - Lifetime, roundtrip efficiency, allowable depth of discharge, etc.  
     - Origin flags for policy adjustments  

4. **Sweep Definition File**

   - Path: `Launch_Files/sweep_1_itc_area.csv`  
   - Defines one or more scenarios for parametric sweeps, including:
     - PV array area  
     - PV ITC rate  
     - Battery ITC rate  
     - Emissions offset price  
     - Flags for enabling/disabling certain constraints (e.g., export, interconnection limit)  

   An example file is included in the repository and can be used as a template for creating new sweep files.

> **Important:** Do not change column names in these CSVs unless you also update the corresponding Python/AMPL code. Use the existing files as templates when building your own datasets.

---

## Batch Sweep Processing

The repository supports sweeps over multiple parameter configurations, defined in CSV files under `Launch_Files/`.

### Single-Sweep Usage (CLI)

As shown in the Quick Start:

    microgrid-sweep-run \
      --sweep Launch_Files/sweep_1_itc_area.csv \
      --run-id demo_sweep \
      --sheet-id Demo \
      --output Outputs/Demo_Run \
      --insolation-mult 1.0

### Multiple Sweeps / Batch Runs

For more complex experiments, you can:

- Create multiple sweep CSVs in `Launch_Files/` (e.g., `sweep_itc_area.csv`, `sweep_emissions.csv`).  
- Use your own driver script or the provided `parallel_sweep.py` (if configured) to iterate over these sweep files and launch them sequentially or in parallel, writing a log per run.

Example (conceptual) Python usage:

    from microgrid.scripts.run_sweep import run_sweep_main

    sweeps = [
        ("Launch_Files/sweep_1_itc_area.csv", "itc_area"),
        ("Launch_Files/sweep_2_emissions.csv", "emissions"),
    ]

    for sweep_csv, tag in sweeps:
        run_sweep_main(
            sweep_csv=sweep_csv,
            run_id=f"batch_{tag}",
            sheet_id=tag.upper(),
            output_dir=f"Outputs/batch_{tag}",
            insolation_mult=1.0,
        )

This pattern allows you to build your own “multi-sweep” batch experiments analogous to multi-location or multi-scenario optimization.

### Applications

- Parametric analysis of policy levers (ITC, emissions credits).  
- Sensitivity analysis on PV array area and interconnection limits.  
- Scenario design for microgrid economics and emissions performance.

---

## API Reference

The project includes an optional FastAPI app for running sweeps via a simple web interface.

### Starting the API

From the repository root (with your virtual environment activated and AMPL configured):

    uvicorn microgrid.api.main:app --reload

By default this launches the app at:

    http://127.0.0.1:8000/

### Endpoints

- `GET /`  
  - Serves a minimal HTML front-end (`frontend/index.html`) that lets you upload a sweep CSV and trigger a run.

- `POST /run-sweep`  
  - Accepts a file upload (`multipart/form-data`) containing a sweep CSV.  
  - Invokes the same backend logic as `microgrid-sweep-run`.  
  - Packages the resulting output directory into a ZIP file and returns it as a download.

- `GET /docs`  
  - FastAPI’s automatically generated API documentation (Swagger UI), useful for inspecting available endpoints and testing them interactively.

> Note: The web API is intended for local use. It does **not** require or provide any external web services; all computation occurs on your machine using your local AMPL installation.

---

## Resource Data Management

Resource and configuration data are managed via simple CSV files:

- **Input files** must reside (by default) under:
  - `Input_Files/` for hourly and technology data.  
  - `Launch_Files/` for sweep definitions.

- **Output files** are written to:
  - `Outputs/<run_id>.../` by default (or to the directory specified via `--output` / `output_dir`).

You can change these conventions by:

- Passing explicit paths to CLI arguments (`--sweep`, `--output`).  
- Modifying the relevant path-handling logic in `model_helpers.py` and the script modules if you want a different directory structure.

---

## Key Features Detail

### Tariff and Economic Modeling

- Hourly simulation aligns dispatch decisions with tariff periods (e.g., peak/off-peak, demand charge windows).  
- Monthly and annual costs are computed from hourly outputs, enabling net present cost and cost-of-energy style analysis (depending on the post-processing you perform on the scalar outputs).

### Technology Selection and Origin Policy

- PV and BESS technologies are modeled as discrete options with specified costs, efficiencies, and lifetimes.  
- Origin-based flags and multipliers enable:
  - Applying ITC only to certain technologies or origins.  
  - Adjusting capital costs or incentives based on origin.

### Scenario and Sensitivity Analysis

- Sweeps allow you to systematically vary:
  - PV ITC, battery ITC, and emissions offset prices.  
  - PV array area (within interconnection limits).  
- This supports:
  - “As-is” baseline analyses (no incentives, no emissions price).  
  - Policy counterfactuals (e.g., comparing different ITC levels).  
  - Sensitivity analyses to resource or load assumptions via modifiers (e.g., insolation multiplier).

---

## Results Output

A completed sweep run typically generates:

- **Excel Workbooks** for each configuration or sweep:
  - `H_*` sheets:
    - Hourly PV generation, battery charging/discharging, state of charge.  
    - Grid imports/exports, unmet load (if applicable).  
    - Hourly cost components and emissions.  

  - `M_*` sheets:
    - Aggregated monthly energy consumption and demand.  
    - Monthly cost components (energy charges, demand charges, fixed charges).  
    - High-level monthly summaries.

- **Scalar Summary Files**:
  - Per-configuration scalar metrics such as:
    - Installed PV and BESS capacities.  
    - Annual energy, demand, and total cost.  
    - Emissions totals and, where applicable, emissions-cost impacts.  

- **Sweep Summary**:
  - A consolidated CSV/Excel file combining key outputs from all configurations in the sweep, suitable for plotting and regression-style analysis.

The exact file names and structure may vary based on your run ID and how you configure the scripts, but all outputs are placed under the chosen `--output` directory for that run.

---

## License

This module is licensed under the **BSD 3-Clause License**.

See the `LICENSE` file in the repository root for the full license text and terms.

---

## Contact

For questions, bug reports, or feature requests:

- Please open an **Issue** on this GitHub repository.
