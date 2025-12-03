# Solar–Storage Co-Optimization

Python + AMPL workflow for co-optimizing solar PV and battery storage sizing and dispatch for a commercial & industrial (C&I) facility, with a focus on tariff-driven economics and emissions abatement.

The code wraps an AMPL mixed-integer linear programming (MILP) model with a Python front-end that:

- Runs **single PV/BESS configurations** or **full parametric sweeps**
- Writes **Excel + CSV outputs** (hourly, monthly, scalar summaries)
- Supports **origin-based ITC and cost adjustments** for PV and battery technologies
- Exposes a **FastAPI endpoint** for launching sweep runs from a lightweight web front-end

This repository underpins a research case study of a manufacturing facility in Medley, Florida (served under FPL’s GSLDT-1 tariff), where the model co-optimizes PV module type and battery chemistry under various ITC and emissions credit scenarios.


---

## 1. Research context (kept from original project intent)

This project was developed as part of a graduate dissertation on **solar-plus-storage microgrid optimization** for a C&I manufacturing facility. The model:

- Uses an **hourly (8,760-step) load and irradiance profile** for the facility
- Co-optimizes:
  - PV technology (e.g., mono-Si PERC, mono-bifacial, CdTe)
  - Battery technology (e.g., Li-ion LFP)
  - PV array area and BESS energy/power size, subject to an interconnection cap
- Evaluates scenarios with:
  - No incentives (Base Case)
  - Investment Tax Credits (ITC) on PV and/or BESS
  - Emissions offset prices and abatement credits

Python scripts in this repo orchestrate sweeps over PV area, ITC rates, and offset prices, and consolidate results into Excel workbooks and CSV summary tables suitable for analysis and figure generation.


---

## 2. Features

- **AMPL MILP model** for solar-plus-storage sizing and dispatch
- **Python wrappers** for:
  - Single configuration runs (`run_single_loop.py`)
  - Sweep runs from CSV (`run_sweep.py`)
  - Parallel/launch orchestration (`parallel_sweep.py`)
- **Structured outputs**:
  - Hourly sheets (`H_*`) with dispatch + cost/emissions columns
  - Monthly sheets (`M_*`) with tariff-based cost breakdowns
  - Scalar summaries per configuration and merged sweep summaries
- **PV/Battery origin policy**:
  - Adjusts costs and ITC based on origin lists and discount multipliers
- **FastAPI endpoint**:
  - `/` – simple HTML front-end
  - `/run-sweep` – upload sweep CSV, run AMPL via Python wrapper, and download results as a ZIP


---

## 3. Repository structure

The core layout is:

```text
Solar-Storage-Co-Optimization/
├─ src/
│  └─ microgrid/
│     ├─ __init__.py
│     ├─ core/
│     │  ├─ __init__.py
│     │  ├─ model_helpers.py        # Paths, AMPL setup, cost helpers, monthly summary, etc.
│     │  ├─ excel_utils.py          # Excel writer for hourly/monthly/scalar sheets
│     │  ├─ logging_utils.py        # Simple logging helpers
│     │  └─ pv_sizing_limits.py     # PV sizing limit utilities
│     ├─ scripts/
│     │  ├─ __init__.py
│     │  ├─ run_single_loop.py      # Single configuration driver (CLI)
│     │  ├─ run_sweep.py            # Sweep driver (CLI)
│     │  └─ parallel_sweep.py       # Launch multiple sweeps and master log
│     ├─ api/
│     │  ├─ __init__.py
│     │  └─ main.py                 # FastAPI app exposing / and /run-sweep
│     └─ solar_storage_model/
│        └─ solar_storage_model.mod # AMPL model (path used in model_helpers)
├─ Input_Files/
│  ├─ Hourly_parameter_data.csv     # Load, irradiance, tariff, emissions, etc.
│  ├─ bi_pv_table.csv               # PV technology data
│  └─ bat_tab_lion.csv              # Battery technology data
├─ Launch_Files/
│  └─ sweep_1_itc_area.csv          # Example sweep definition (A_tot, itc_pv, itc_bat, etc.)
├─ Outputs/
│  └─ ...                           # Excel + CSV results (created at runtime)
├─ frontend/
│  └─ index.html                    # Minimal web UI for uploading a sweep CSV
├─ pyproject.toml
├─ requirements.txt  (optional, if you keep one)
└─ README.md
#4 Run Locally
4.1 Clone the repository (bash)

git clone https://github.com/mcaballero305/Solar-Storage-Co-Optimization.git
cd Solar-Storage-Co-Optimization

4.2 create and activate virtual environment (in powershell)

python -m venv .venv
.venv\Scripts\Activate.ps1

in bash

python3 -m venv .venv
source .venv/bin/activate
4.3 Install package

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .

4.4 Configure local AMPL path
Update AMPL path in code src/microgrid/core/model_helpers.py to the local directory where AMPL is installed

5 Running Online 
## Credentials Required

SSH access to the server at `64.227.58.59` (root privileges)

## Installation & Setup

### 1. Connect to the Server
```bash
ssh root@64.227.58.59
```

### 2. Clone the Repository
```bash
git clone git@github.com:mcaballero305/Solar-Storage-Co-Optimization
```

### 3. Navigate to Project Directory
```bash
cd Solar-Storage-Co-Optimization
```

### 4. Create and Activate Virtual Environment
```bash
python -m venv .venv
source .venv/bin/activate
```

### 5. Install Dependencies
```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .
```

## Testing via CLI
```bash
microgrid-sweep-run \
  --sweep src/microgrid/Launch_Files/sweep_1_itc_area.csv \
  --run-id sweep \
  --sheet-id Sweep \
  --output Outputs/New \
  --insolation-mult 1.0
```
