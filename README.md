# Log-Driven-Gas-Optimization-for-Smart-Contracts

Log-Driven Gas Optimization for Smart Contracts is a local, YAML-configured Python tool that analyzes smart-contract event logs in XES (.xes / .xes.gz) to surface gas-saving opportunities and produce a deterministic, audit-friendly PDF report.

See the Wiki for configuration keys and detector definitions.



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

> **Note:** Use any of the following three smart-contract event logs as input to try the code. They come from the open collection of resources for process mining on blockchain data: https://ingo-weber.github.io/dapp-data/ 
**Recommended:** start with **Augur** (it’s smaller than the others). With Augur you can also run right away and no YAML changes needed; the defaults already match the log (`USER_KEY: "requester"`, `STATUS_KEY: "txSuccessful"`, `GAS_KEY: "gasUsed"`, `GAS_LIMIT_KEY: "gas"`, `LONG_TRACE_IDENTIFIER: "ident:piid"`).

- **Augur** — XES  
  Source: <https://ingo-weber.github.io/dapp-data/data/Augur.xes>  
  Notes: Good medium-sized log for functional checks and pipeline sanity tests.

- **ChickenHunt** — XES (gzipped)  
  Source: <https://github.com/ingo-weber/dapp-data/blob/master/data/Final_ChickenHunt.xes.gz?raw=true>  
  Notes: Compressed XES; demonstrates the tool’s ability to work with typical on-chain game workflows.

- **Forsage** — XES (gzipped)  
  Source: <https://github.com/ingo-weber/dapp-data/blob/master/data/Final_Forsage.xes.gz?raw=true>  
  **Warning:** For memory/safety reasons we analyzed only the **first 155,931 traces** from this log.



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
LOG_FILE_PATH: "./augur.xes"
PDF_OUTPUT_PATH: "./report.pdf"

# --- XES attribute keys (remap to match your log) ---
TIMESTAMP_KEY: "time:timestamp"
ACTIVITY_KEY: "concept:name"
USER_KEY: "requester"
STATUS_KEY: "txSuccessful"
GAS_KEY: "gasUsed"
GAS_LIMIT_KEY: "gas"
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
  high: 220
  medium: 70

# --- Detector thresholds & limits ---
TIME_THRESHOLD_SECONDS: 60
MAX_SEQUENCE_LENGTH: 7
MAX_SEQ_SUGGESTIONS: 5
PERCENTILE: 99
MAX_LONG_TRACE_SUGGESTIONS: 5
MAX_OUT_OF_GAS_SUGGESTIONS: 5

# --- User fallback (when USER_KEY is missing) ---
FALLBACK_USER_FROM_TRACE: false
TRACE_USER_ATTR: "concept:name"
```


