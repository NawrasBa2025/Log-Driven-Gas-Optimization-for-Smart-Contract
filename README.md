# Log-Driven-Gas-Optimization-for-Smart-Contracts

Log-Driven Gas Optimization for Smart Contracts is a local, YAML-configured Python tool that analyzes smart-contract event logs in XES (.xes / .xes.gz) to surface gas-saving opportunities and produce a deterministic, audit-friendly PDF report.

See the Wiki for configuration keys and detector definitions.

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
# --- Paths ---
LOG_FILE_PATH: "./your-file.xes"      
PDF_OUTPUT_PATH: "./report.pdf"

# --- Core XES attribute keys ---
TIMESTAMP_KEY: "time:timestamp"     
ACTIVITY_KEY: "concept:name"        
USER_KEY: "org:resource"            

# --- Detectors you want to run ---
features:
  merge: true                        # needs TIMESTAMP_KEY, USER_KEY, ACTIVITY_KEY, TIME_THRESHOLD_SECONDS
  redundancy: false                  # needs ACTIVITY_KEY, USER_KEY 
  sequence: true                     # needs TIMESTAMP_KEY, USER_KEY, ACTIVITY_KEY, TIME_THRESHOLD_SECONDS, MAX_SEQUENCE_LENGTH
  trace_length: false                # needs PERCENTILE, LONG_TRACE_IDENTIFIER
  out_of_gas_exception: true         # needs STATUS_KEY, GAS_KEY, GAS_LIMIT_KEY

# --- Thresholds (used by enabled detectors) ---
TIME_THRESHOLD_SECONDS: 10          # merge & sequence window
MAX_SEQUENCE_LENGTH: 7              # sequence upper bound
PERCENTILE: 99                      # long-trace cutoff

# --- Only needed if you enable out_of_gas_exception ---
STATUS_KEY: "status"
GAS_KEY: "gas"
GAS_LIMIT_KEY: "gasLimit"

# --- Severity (counts -> Low/Medium/High) ---
Severity_limits:
  high: 100                          
  medium: 50

# --- If your log lacks a per-event user, derive it from a trace attribute ---
FALLBACK_USER_FROM_TRACE: true
TRACE_USER_ATTR: "concept:name"

# --- Miner pages (require Graphviz) ---
 miners:
    alpha_miner: false
    heuristics_miner: false
    inductive_miner: false
```


