# Log-Driven-Gas-Optimization-for-Smart-Contracts

Log-Driven Gas Optimization for Smart Contracts is a local, YAML-configured Python tool that analyzes smart-contract event logs in XES (.xes / .xes.gz) to surface gas-saving opportunities and produce a deterministic, audit-friendly PDF report.

See the Wiki for configuration keys and detector definitions.

---
> **⚠️ Memory & performance warning**  
> XES logs can be very large. Loading and analyzing big logs may consume significant RAM and can freeze or crash your system if the hardware is insufficient.  
> **Tips:** start with a smaller sample (e.g., first *N* traces), filter the log before analysis, close memory‑hungry apps, and prefer chunked/streamed processing when possible.

---

## Project structure

```text
.
├── Automated/
│   ├── README.md                 # Notes for automated runs
│   ├── automated-config.yaml     # Example config for automated runs
│   └── automated.py              # Batch runner / CLI entry point
├── SmartContractAnalyzer.py      # Core analysis logic
├── config.yaml                   # Default configuration
├── LICENSE
└── README.md                     # This file
```

---

## Event log datasets (XES)

These are the smart-contract execution logs used during development and testing:

- **Augur** — XES  
  Source: <https://ingo-weber.github.io/dapp-data/data/Augur.xes>  
  Notes: Good medium-sized log for functional checks and pipeline sanity tests.

- **ChickenHunt** — XES (gzipped)  
  Source: <https://github.com/ingo-weber/dapp-data/blob/master/data/Final_ChickenHunt.xes.gz?raw=true>  
  Notes: Compressed XES; demonstrates the tool’s ability to work with typical on-chain game workflows.

- **Forsage** — XES (gzipped)  
  Source: <https://github.com/ingo-weber/dapp-data/blob/master/data/Final_Forsage.xes.gz?raw=true>  
  **Warning:** For memory/safety reasons we analyzed only the **first 155,931 traces** from this log.

> If you use other logs, prefer `.xes` or `.xes.gz`. Many XES toolkits can read gzipped files directly.

---

## Installation

**Requirements**
- Python **3.10+**
- Graphviz for miner diagrams

**Create a virtual environment (recommended)**
```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows:
.\.venv\Scripts\activate
```

**Install Python dependencies**
```bash
python -m pip install -U pip
pip install pm4py reportlab matplotlib pillow pyyaml numpy
```

**Install Graphviz (for miner diagrams)**
- macOS: `brew install graphviz`
- Ubuntu/Debian: `sudo apt-get install graphviz`
- Windows (Chocolatey): `choco install graphviz`

### Forcing a system-wide install (not recommended)
If your system is an externally managed Python (PEP 668) and you *must* install without a virtualenv, you can force pip with:

```bash
pip install pm4py reportlab matplotlib pillow pyyaml numpy --break-system-packages
```

> ⚠️ Use `--break-system-packages` only if you understand the risks. Prefer a virtual environment or pipx when possible.

---

## Run

1) Place `config.yaml` in the working directory (same folder as the script).  
2) Run the analyzer:

```bash
python3 ./SmartContractAnalyzer.py
```

The script loads `config.yaml`, processes the log, and writes the PDF report to the path you configure.

---

## Required config to run 

Create `config.yaml` with these following keys. 

```yaml
# --- File paths ---
LOG_FILE_PATH: "./your-log.xes"
PDF_OUTPUT_PATH: "./report.pdf"

# --- XES attribute keys (remap to match your log) ---
TIMESTAMP_KEY: "time:timestamp"
ACTIVITY_KEY: "concept:name"
USER_KEY: "org:resource"
STATUS_KEY: "status"
GAS_KEY: "gas"
GAS_LIMIT_KEY: "gasLimit"
LONG_TRACE_IDENTIFIER: "ident:piid"

# --- Feature flags (enable/disable detectors) ---
features:
  merge: true
  redundancy: true
  trace_length: true
  sequence: true
  out_of_gas_exception: false

# --- Miner toggles (optional process models pages) ---
miners:
  alpha_miner: false
  heuristics_miner: false
  inductive_miner: true

# --- Severity bucketing (counts -> Low/Medium/High) ---
Severity_limits:
  high: 3
  medium: 2

# --- Detector thresholds & limits ---
TIME_THRESHOLD_SECONDS: 10
MAX_SEQUENCE_LENGTH: 7
MAX_SEQ_SUGGESTIONS: 3
PERCENTILE: 80
NUM_LONGEST_TRACES: 5
MAX_OUT_OF_GAS_SUGGESTIONS: 5

# --- User fallback (when USER_KEY is missing) ---
FALLBACK_USER_FROM_TRACE: false
TRACE_USER_ATTR: "concept:name"
```


