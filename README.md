olar Storage Co-Optimization

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
