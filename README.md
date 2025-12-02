# Dissertation 

## Setup

# Installation
git clone git@github.com:mcaballero305/Solar-Storage-Co-Optimization


cd Solar-Storage-Co-Optimization

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip setuptools wheel
python -m pip install -e .


## Testing via CLI 

microgrid-single-run --help

microgrid-single-run `
  --pv "Mono Si PERC" `
  --bat "LFP_2h" `
  --offset_price 0.0 `
  --excel_out outputs\excel\single_run_test.xlsx

