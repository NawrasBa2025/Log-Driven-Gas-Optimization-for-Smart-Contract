
# README.md — Automated Multi-Run Test for Smart Contract Analyzer

## Overview
This repo runs an **automated sweep of experiments** over an event log (`.xes`) using a single driver script and a YAML config. Each run computes:
- Merge/redundancy/sequence stats (feature-gated)
- **Percentile-based** trace-length metrics:
  - `LongTraces` – count of traces above that threshold

The sweep is defined in `automated-config.yaml` under `runs:`. Results are written to JSON and also echoed as a table.

---

## Requirements
- **Python** 3.9+ (3.10+ recommended)
- Packages: `numpy`, `pandas`, `pyyaml`

---

## Installation

### Option A — Virtual environment (recommended)
```bash
python -m venv .venv
# Linux/macOS
source .venv/bin/activate
# Windows (PowerShell)
.\.venv\Scripts\Activate.ps1

pip install --upgrade pip
pip install numpy pandas pyyaml
```

### Option B — System Python (when venv is not possible)
> ⚠️ On Debian/Ubuntu with newer `pip`, you may need to force install into the system environment:
```bash
pip install --upgrade pip
pip install numpy pandas pyyaml --break-system-packages
```

---

## Files
- `automated.py` — driver script (invoke this)
- `automated-config.yaml` — configuration for the sweep
- `your-file.xes` — your input event log (path configurable)

If your script name differs, replace it accordingly in the commands below.

---

## Quick Start

1) **Place your XES log** at the path specified by `LOG_FILE_PATH` (default: `./your-file.xes`).

2) **Check the config** (see the next section). Minimal working example is provided below.

3) **Run the sweep:**
```bash
python automated.py.py
```

4) **Results**:
- JSON written to `OUTPUT_NAME` (default: `analysis_summary.json` or `pid0.json`, depending on your config)
- A summary table printed to stdout

---

## Configuration (`automated-config.yaml`)

```yaml
LOG_FILE_PATH: ./your-file.xes          # path to your XES log
OUTPUT_NAME: analysis_summary.json   # where results will be written

# default keys in your XES file (change if your log uses different ones)
TIMESTAMP_KEY: time:timestamp
ACTIVITY_KEY: concept:name
USER_KEY: org:resource

# enable/disable features
features:
  merge: true
  redundancy: true
  sequence: true

# global default percentile (can be overridden per run)
PERCENTILE: 99

# list of runs to execute automatically
runs:
  - name: R1
    TIME_THRESHOLD_SECONDS: 60
    MAX_SEQUENCE_LENGTH: 5
    # PERCENTILE: 95   # optional per-run override
  - name: R2
    TIME_THRESHOLD_SECONDS: 300
    MAX_SEQUENCE_LENGTH: 7
```

### Key notes
- `PERCENTILE` (top-level): default percentile applied to all runs (e.g., `99`).
- `runs[].PERCENTILE` (optional): override for a specific run.
- `TIME_THRESHOLD_SECONDS`: maximum time window for merges/sequences.
- `MAX_SEQUENCE_LENGTH`: upper bound of sequence window length considered.
- `features`: toggle analysis modules:
  - `merge`: count adjacent events (same user) within the time threshold.
  - `redundancy`: count consecutive identical activities (same user).
  - `sequence`: mine sequences up to `MAX_SEQUENCE_LENGTH` within the time threshold.

---

## Output schema

Each run in the output JSON is an object with:
```json
{
  "Run": "R1",
  "TIME (s)": 60,
  "MAX_SEQ_LEN": 5,
  "PERCENTILE": 99,
  "Pctl_Threshold": 42,
  "Long_Traces": 13,
  "Merges": 27,
  "Sequenzen": 8
}
```

**Field definitions**
- `Run`: run name from `runs[].name`.
- `TIME (s)`: time threshold used for the run.
- `MAX_SEQ_LEN`: max sequence length considered.
- `PERCENTILE`: percentile used (global or per-run override).
- `Pctl_Threshold`: length at that percentile among all trace lengths.
- `LongTraces(>Pctl)`: number of traces strictly longer than `Pctl_Threshold`.
- `Merges`: total number of merge suggestions found.
- `Sequenzen`: number of qualifying sequences (appearing at least twice), capped by `maximal_sequence_suggestion` if configured.

---

## Automated Test / Smoke Test

If you want a quick end-to-end check without real data, you can create a tiny XES and run the pipeline.

1) **Create a tiny XES** (save as `your-file.xes` next to the script):
```xml
<?xml version="1.0" encoding="UTF-8" ?>
<log xes.version="1.0" xes.features="nested-attributes" openxes.version="1.0RC7" xmlns="http://www.xes-standard.org/">
  <trace>
    <string key="concept:name" value="case_1"/>
    <event>
      <string key="concept:name" value="A"/>
      <string key="org:resource" value="u1"/>
      <date key="time:timestamp" value="2024-01-01T00:00:00Z"/>
    </event>
    <event>
      <string key="concept:name" value="B"/>
      <string key="org:resource" value="u1"/>
      <date key="time:timestamp" value="2024-01-01T00:00:10Z"/>
    </event>
    <event>
      <string key="concept:name" value="B"/>
      <string key="org:resource" value="u1"/>
      <date key="time:timestamp" value="2024-01-01T00:00:15Z"/>
    </event>
  </trace>
  <trace>
    <string key="concept:name" value="case_2"/>
    <event>
      <string key="concept:name" value="A"/>
      <string key="org:resource" value="u2"/>
      <date key="time:timestamp" value="2024-01-01T00:01:00Z"/>
    </event>
    <event>
      <string key="concept:name" value="C"/>
      <string key="org:resource" value="u2"/>
      <date key="time:timestamp" value="2024-01-01T00:01:30Z"/>
    </event>
  </trace>
</log>
```

2) **Use this config** (save as `automated-config.yaml`):
```yaml
LOG_FILE_PATH: ./your-file.xes
OUTPUT_NAME: analysis_summary.json
TIMESTAMP_KEY: time:timestamp
ACTIVITY_KEY: concept:name
USER_KEY: org:resource

features:
  merge: true
  redundancy: true
  sequence: true

PERCENTILE: 90

runs:
  - name: Smoke
    TIME_THRESHOLD_SECONDS: 60
    MAX_SEQUENCE_LENGTH: 5
```

3) **Run**:
```bash
python automated.py.py
cat analysis_summary.json
```

Expected: one JSON object with the fields described above and non-zero `Merges`, `Sequenzen`, and percentile stats.

---

## CI Integration (optional)

### GitHub Actions example
Create `.github/workflows/test.yml`:
```yaml
name: automated-test
on: [push, pull_request]

jobs:
  sweep:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install numpy pandas pyyaml --break-system-packages || pip install numpy pandas pyyaml
      - run: python multi-run-v2.py
      - run: |
          test -f analysis_summary.json
          python - <<'PY'
import json
with open("analysis_summary.json") as f:
    data = json.load(f)
assert isinstance(data, list) and len(data) >= 1
required = {"Run","TIME (s)","MAX_SEQ_LEN","PERCENTILE","Pctl_Threshold","LongTraces(>Pctl)","Merges","Sequenzen"}
assert required.issubset(data[0].keys())
print("✅ basic schema ok")
PY
```

---

## Tips & Troubleshooting

- **File not found**: Ensure `LOG_FILE_PATH` points to a valid `.xes` file.
- **YAML errors**: Validate indentation; make sure `runs:` is a list of maps.
- **Timestamp parsing**: The script expects ISO-8601 (e.g., `2024-01-01T12:34:56Z`). Adjust `TIMESTAMP_KEY` if your log differs.
- **Large logs**: Consider running in a venv and give Python more memory if needed; you can also split logs and run multiple configs.
- **Per-run percentile**: Add `PERCENTILE` under any `runs[]` item to override the global default.

---

## License
Add your project license here.

---

## Contact
Questions or issues? Open an issue or ping the maintainer.
