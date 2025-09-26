import os
import gzip
import io
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict, Counter
import sys, platform, hashlib, tempfile

import numpy as np
import yaml
from PIL import Image
from matplotlib import pyplot as plt

# ReportLab – High-level (Platypus)
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    Frame, PageTemplate, NextPageTemplate, PageBreak, Image as RLImage, KeepTogether
)

# PM4Py
from pm4py.objects.log.importer.xes import importer as xes_importer
from pm4py.algo.discovery.alpha import algorithm as alpha_miner
from pm4py.algo.discovery.heuristics import algorithm as heuristics_miner
from pm4py.algo.discovery.inductive import algorithm as inductive_miner
from pm4py.objects.conversion.heuristics_net import converter as hn_converter
from pm4py.visualization.petri_net import visualizer as pn_visualizer
from pm4py.objects.conversion.process_tree import converter as pt_converter
from pm4py.algo.evaluation.replay_fitness import algorithm as fitness_evaluator
from pm4py.algo.evaluation.precision import algorithm as precision_evaluator
from pm4py.algo.evaluation.generalization import algorithm as generalization_evaluator

import matplotlib
import reportlab
import pm4py
import PIL

# ========================
# Config
# ========================
# All configuration is loaded from config.yaml in the current directory. change parameter to match your environment
# note that you can define default values for missing keys
CONFIG_PATH = "config.yaml"

def load_config(config_path):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

config = load_config(CONFIG_PATH)

# FILE PATHS
LOG_FILE_PATH = config.get("LOG_FILE_PATH", "./pid0.xes")           # Input XES file (supports .xes and .xes.gz)
PDF_OUTPUT_PATH = config.get("PDF_OUTPUT_PATH", "./final_report.pdf") # Output PDF

# DETECTOR TIMING / ATTR KEYS
TIME_THRESHOLD_SECONDS = int(config.get("TIME_THRESHOLD_SECONDS", 60))  # Merge/Sequence time window (sec)
TIMESTAMP_KEY = config.get("TIMESTAMP_KEY", "time:timestamp")          # XES key for event timestamp
ACTIVITY_KEY = config.get("ACTIVITY_KEY", "concept:name")              # XES key for activity label
USER_KEY = config.get("USER_KEY", "org:resource")                      # XES key for resource/user
STATUS_KEY = config.get("STATUS_KEY", "status")                        # XES key used by out-of-gas detector
GAS_KEY = config.get("GAS_KEY", "gas")                                 # XES key used by out-of-gas detector
GAS_LIMIT_KEY = config.get("GAS_LIMIT_KEY", "gasLimit")                # XES key used by out-of-gas detector

LONG_TRACE_IDENTIFIER = config.get("LONG_TRACE_IDENTIFIER", "blockNumber")  # XES key used to identify long traces (for reporting)
MAX_LONG_TRACE_SUGGESTIONS = int(config.get("MAX_LONG_TRACE_SUGGESTIONS", 5))           # How many longest traces to list in the PDF
PERCENTILE = int(config.get("PERCENTILE", 99))                          # Percentile defining "long trace" threshold
MAX_OUT_OF_GAS_SUGGESTIONS = int(config.get("MAX_OUT_OF_GAS_SUGGESTIONS", 10)) # Max OOG events shown in report

# FEATURE FLAGS / LIMITS
features = config.get("features", {})                                   # Toggle detectors: merge/redundancy/sequence/out_of_gas_exception
MAX_SEQ_SUGGESTIONS = config.get("MAX_SEQ_SUGGESTIONS", 10)  # Max sequences shown in report
MAX_L = int(config.get("MAX_SEQUENCE_LENGTH", 5))                        # Max sequence length checked
FALLBACK_USER_FROM_TRACE = config.get("FALLBACK_USER_FROM_TRACE", True)  # Use trace attr as user when org:resource missing
TRACE_USER_ATTR = config.get("TRACE_USER_ATTR", "concept:name")         # Trace-level attr to use as user fallback
SEVERITY_LIMITS = config.get("Severity_limits", {"heigh":3, "medium":2})  # Thresholds for severity levels
# Create output directory (robust)
out_dir = os.path.dirname(PDF_OUTPUT_PATH)
if out_dir:
    os.makedirs(out_dir, exist_ok=True)

# ========================
# Utils
# ========================

def parse_timestamp(ts):
    """Parse various ISO / simple date formats to datetime (tz-aware if ISO)."""
    if not ts:
        return None
    ts = str(ts).strip().replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(ts)
    except Exception:
        pass
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(ts, fmt)
        except Exception:
            continue
    return None

def safe_get_version(mod, attr_names=("__version__", "Version", "VERSION")):
    for a in attr_names:
        v = getattr(mod, a, None)
        if v:
            return str(v)
    return "n/a"

def get_runtime_context():
    """Collect runtime/software versions for the reproducibility footnote."""
    tz = datetime.now().astimezone().tzinfo
    return {
        "run_started_at": datetime.now().isoformat(timespec="seconds"),
        "python": sys.version.split()[0],
        "os": platform.system(),
        "os_release": platform.release(),
        "arch": platform.machine(),
        "timezone": str(tz) if tz else "n/a",
        "numpy": safe_get_version(np),
        "pyyaml": safe_get_version(yaml),
        "matplotlib": safe_get_version(matplotlib),
        "pillow": safe_get_version(PIL),
        "reportlab": safe_get_version(reportlab),
        "pm4py": safe_get_version(pm4py),
    }

def build_param_snapshot(config, meta, runtime_ctx):
    """Render a YAML snapshot (config + runtime) for the PDF footnote."""
    cfg_export = {
        "LOG_FILE_PATH": LOG_FILE_PATH,
        "PDF_OUTPUT_PATH": PDF_OUTPUT_PATH,
        "TIME_THRESHOLD_SECONDS": TIME_THRESHOLD_SECONDS,
        "TIMESTAMP_KEY": TIMESTAMP_KEY,
        "ACTIVITY_KEY": ACTIVITY_KEY,
        "USER_KEY": USER_KEY,
        "STATUS_KEY": STATUS_KEY,
        "GAS_KEY": GAS_KEY,
        "GAS_LIMIT_KEY": GAS_LIMIT_KEY,
        "MAX_LONG_TRACE_SUGGESTIONS": MAX_LONG_TRACE_SUGGESTIONS,
        "MAX_SEQ_SUGGESTIONS": MAX_SEQ_SUGGESTIONS,
        "MAX_SEQUENCE_LENGTH": MAX_L,
        "PERCENTILE": PERCENTILE,
        "MAX_OUT_OF_GAS_SUGGESTIONS": MAX_OUT_OF_GAS_SUGGESTIONS,
        "LONG_TRACE_IDENTIFIER": LONG_TRACE_IDENTIFIER,
        "FALLBACK_USER_FROM_TRACE": FALLBACK_USER_FROM_TRACE,
        "TRACE_USER_ATTR": TRACE_USER_ATTR,
        "features": config.get("features", {}),
        "miners": config.get("miners", {}),
        "SEVERITY_LIMITS": config.get("Severity_limits", {}),
    }
    snapshot = {"run": runtime_ctx, "config_snapshot": cfg_export}
    return yaml.safe_dump(snapshot, sort_keys=False, allow_unicode=True)

def parse_xes_tree(file_path):
    """Read .xes or .xes.gz into an ElementTree."""
    if str(file_path).lower().endswith(".gz"):
        with gzip.open(file_path, "rb") as f:
            data = f.read()
        return ET.parse(io.BytesIO(data))
    return ET.parse(file_path)

def file_sha256(path, chunk_size=8192):
    """Compute SHA256 – used if you want to include file integrity in the footnote."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


# DETECTOR:
# 1 Out-of-Gas Exception
# 2 Redundancy (same activity repeated back-to-back per user in a trace)
# 3 Merge candidates (very short time between two consecutive user events)
# 4 Short-time Sequences (windows of 3..MAX_L inside threshold)
# 5 Long Traces
# Notes:
# - "user" falls back to the trace attribute TRACE_USER_ATTR when USER_KEY is missing.
#    This keeps detectors consistent when org:resource is absent.
# - Feature flags in `features` can disable any detector without code changes.

def generate_analysis_and_charts(file_path):
    tree = parse_xes_tree(file_path)
    root = tree.getroot()
    traces = root.findall('.//trace')

    trace_attrs_by_idx = {}  # NEW: keep trace-level attributes per trace
    raw_merge_suggestions = defaultdict(int)
    redundant = defaultdict(int)
    sequences = defaultdict(int)
    severity_levels = Counter()
    redundancy_activity_count = Counter()
    merge_activity_count = Counter()
    out_of_gas_events = []
    trace_lengths = []
    trace_groups = defaultdict(list)
    trace_user_fallback = {}

    # --- Group events by trace and cache a user fallback (for missing org:resource) ---
    for idx, trace in enumerate(traces):
        trace_attrs = {}
        for child in trace:
            if child.tag != 'event':
                k = child.attrib.get('key')
                v = child.attrib.get('value')
                if k is not None:
                    trace_attrs[k] = v
        trace_attrs_by_idx[idx] = trace_attrs  # NEW: store attributes for later
        fb_user = None
        if FALLBACK_USER_FROM_TRACE:
            fb_user = trace_attrs.get(TRACE_USER_ATTR) or trace_attrs.get("concept:name") or f"trace_{idx}"
        trace_user_fallback[idx] = fb_user

        for event in trace.findall('event'):
            evt_data = {child.attrib.get('key'): child.attrib.get('value') for child in event}
            trace_groups[idx].append(evt_data)

    # --- Per-trace detectors ---
    for trace_idx, events in trace_groups.items():
        trace_lengths.append(len(events))

        # Out-of-Gas – independent of user grouping
        for event in events:
            activity = event.get(ACTIVITY_KEY)
            timestamp = parse_timestamp(event.get(TIMESTAMP_KEY))
            status = event.get(STATUS_KEY)
            gas = event.get(GAS_KEY)
            gas_limit = event.get(GAS_LIMIT_KEY)
            if features.get('out_of_gas_exception', True):
                try:
                    # DETECTOR: OOG if tx failed (status==0x0) AND gas used hit gasLimit
                    if (status == "0x0" or status == "false") and gas and gas_limit and int(gas) == int(gas_limit):
                        out_of_gas_events.append((activity, timestamp, gas, gas_limit))
                except ValueError:
                    # Non-numeric gas values are ignored silently
                    pass

        # Group events by user (using fallback) to evaluate redundancy/merge/sequence coherently
        user_event_map = defaultdict(list)
        fb_user = trace_user_fallback.get(trace_idx)
        for event in events:
            user = event.get(USER_KEY) or fb_user or f"trace_{trace_idx}"
            user_event_map[user].append(event)

        for user, user_events in user_event_map.items():
            user_events.sort(key=lambda x: parse_timestamp(x.get(TIMESTAMP_KEY)))
            activity_list = []
            timestamp_list = []
            prev_event = None
            for e in user_events:
                activity = e.get(ACTIVITY_KEY)
                timestamp = parse_timestamp(e.get(TIMESTAMP_KEY))
                if prev_event:
                    prev_activity = prev_event.get(ACTIVITY_KEY)
                    prev_timestamp = parse_timestamp(prev_event.get(TIMESTAMP_KEY))

                    # 2 Redundancy: same activity back-to-back
                    if activity == prev_activity and features.get('redundancy', True):
                        redundant[activity] += 1
                        redundancy_activity_count[activity] += 1

                    # 3 Merge candidate: two consecutive events within TIME_THRESHOLD_SECONDS
                    if prev_timestamp and timestamp and 0 < (timestamp - prev_timestamp).total_seconds() <= TIME_THRESHOLD_SECONDS:
                        if features.get('merge', True):
                            raw_merge_suggestions[(prev_activity, activity)] += 1
                            merge_activity_count[f"{prev_activity} → {activity}"] += 1

                activity_list.append(activity)
                timestamp_list.append(timestamp)
                prev_event = e

            # 4 Short-time sequences: sliding window 3..MAX_L within TIME_THRESHOLD_SECONDS
            n = len(activity_list)
            for window_size in range(3, min(n, MAX_L) + 1):
                for i in range(n - window_size + 1):
                    win_act = activity_list[i:i + window_size]
                    win_ts = timestamp_list[i:i + window_size]
                    if (win_ts[0] is not None and
                        win_ts[-1] is not None and
                        0 < (win_ts[-1] - win_ts[0]).total_seconds() <= TIME_THRESHOLD_SECONDS and
                        features.get('sequence', True)):
                        sequences[tuple(win_act)] += 1

    # 5 Long traces: define threshold at chosen percentile
    trace_length_enabled = features.get('trace_length', True)
    trace_length_threshold = int(np.percentile(trace_lengths, PERCENTILE)) if trace_lengths else 0
    if trace_length_enabled:
        long_traces = [(idx, len(evts)) for idx, evts in trace_groups.items()
                       if len(evts) > trace_length_threshold]
        top_long_traces = sorted(long_traces, key=lambda x: -x[1])[:MAX_LONG_TRACE_SUGGESTIONS]
    else:
        long_traces = []
        top_long_traces = []
    # Map counts to severity buckets for reporting
    def sev_from_count(cnt):
        if cnt >= SEVERITY_LIMITS.get('heigh',3):
            return "High"
        if cnt >= SEVERITY_LIMITS.get('medium',2):
            return "Medium"
        return "Low"

    # Group findings for the PDF section builder
    grouped = {
        "Merges": [],
        "Redundancy": [],
        "Sequences": [],
        "Trace Length": [],
        "Out-of-Gas": []
    }

    for (a1, a2), count in raw_merge_suggestions.items():
        sev = sev_from_count(count)
        grouped["Merges"].append({"sev": sev, "count": count, "text": f"{count}× {a1} → {a2}"})

    for a, count in redundant.items():
        #    if count >=  SEVERITY_LIMITS.get('low', 1):
        sev = sev_from_count(count)
        grouped["Redundancy"].append({"sev": sev, "count": count, "text": f"'{a}' {count}× redundant"})

    sequence_candidates = [(seq, count) for seq, count in sequences.items() if count >= 2]
    sequence_candidates.sort(key=lambda x: (-x[1], -len(x[0]), tuple(x[0])))
    if isinstance(MAX_SEQ_SUGGESTIONS, int) and MAX_SEQ_SUGGESTIONS >= 0:
        sequence_candidates = sequence_candidates[:MAX_SEQ_SUGGESTIONS]
    for seq, count in sequence_candidates:
        sev = "High" if count >= SEVERITY_LIMITS.get('heigh', 5) else "Medium"
        grouped["Sequences"].append({"sev": sev, "count": count, "text": f"{count}× {' → '.join(seq)}"})

    if features.get('out_of_gas_exception', True):
        # Show only the most recent OOG events, capped by MAX_OUT_OF_GAS_SUGGESTIONS
        # Sort by timestamp desc; entries with missing timestamps go last.
        ordered_oog = sorted(
            out_of_gas_events,
            key=lambda t: (t[1] is None, t[1]),
            reverse=True
        )[:MAX_OUT_OF_GAS_SUGGESTIONS]
        for activity, timestamp, gas, gas_limit in ordered_oog:
            grouped["Out-of-Gas"].append({
                "sev": "High",
                "count": 1,
                "text": f"'{activity}' @ {timestamp} (gas==gasLimit=={gas})"
            })

    for trace_idx, length in top_long_traces:
        ident_val = trace_attrs_by_idx.get(trace_idx, {}).get(LONG_TRACE_IDENTIFIER)
        ident_chunk = (
            f'/ Identifier : key="{LONG_TRACE_IDENTIFIER}" value="{ident_val}"'
            if ident_val not in (None, "")
            else ""
        )
    if trace_length_enabled:
        for trace_idx, length in top_long_traces:
            grouped["Trace Length"].append({
                "sev": "High",
                "count": length,
                "text": f"Trace #{trace_idx}: {length} activities (threshold {trace_length_threshold})"
            })

    # Severity distribution for charts
    severity_levels = Counter()
    for cat_items in grouped.values():
        for it in cat_items:
            lbl = it["sev"].split()[-1]  # High/Medium/Low
            severity_levels[lbl] += 1

    # Summary box for the PDF
    num_traces_above_threshold = len(long_traces)
    max_traces_to_show = min(MAX_LONG_TRACE_SUGGESTIONS, num_traces_above_threshold)
    oog_shown = min(MAX_OUT_OF_GAS_SUGGESTIONS, len(out_of_gas_events))
    summary = {
        "Traces analyzed": len(traces),
        "Merges identified": sum(raw_merge_suggestions.values()),
        "Redundancies identified": sum(redundant.values()),
        "Sequences identified": f"{len(sequences)} (shown: {len(sequence_candidates)})",
        "Out-of-Gas Exceptions": f"{len(out_of_gas_events)} (shown: {oog_shown})",
        "Long traces": (f"{num_traces_above_threshold} (shown: {max_traces_to_show})"
                        if trace_length_enabled else "disabled"),
    }
    meta = {"trace_length_threshold": trace_length_threshold, "trace_length_percentile": PERCENTILE}

    chart_paths = generate_temp_charts(redundancy_activity_count, merge_activity_count, severity_levels)
    return grouped, summary, chart_paths, meta

# ========================
# Charts drawing
# ========================
# produce temporary PNGs for the PDF.
# Each chart is optional depending on available data

def generate_temp_charts(redundancy_data, merge_data, severity_data):
    chart_paths = {}

    def save_chart(fig_func, filename):
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        tmp.close()
        fig_func(tmp.name)
        chart_paths[filename] = tmp.name

    def plot_redundancy(path):
        if redundancy_data:
            labels, values = zip(*redundancy_data.items())
            plt.figure(figsize=(8, 4))
            plt.bar(labels, values)
            plt.xticks(rotation=45, ha='right')
            plt.title("Top redundant activities")
            plt.tight_layout()
            plt.savefig(path)
            plt.close()

    def plot_merge(path):
        if merge_data:
            labels, values = zip(*merge_data.items())
            plt.figure(figsize=(8, 4))
            plt.bar(labels, values)
            plt.xticks(rotation=45, ha='right')
            plt.title("Merges per activity")
            plt.tight_layout()
            plt.savefig(path)
            plt.close()

    def plot_severity(path):
        if severity_data:
            labels, sizes = zip(*severity_data.items())
            plt.figure(figsize=(6, 6))
            plt.pie(sizes, labels=labels, autopct='%1.1f%%', startangle=140)
            plt.title("Severity distribution")
            plt.tight_layout()
            plt.savefig(path)
            plt.close()

    save_chart(plot_redundancy, "redundant")
    save_chart(plot_merge, "merge")
    save_chart(plot_severity, "severity")
    return chart_paths

# ========================
# Process Models
# ========================
# Uses PM4Py miners to render Petri nets into PNG files that are later placed
# on separate pages in the PDF. Toggle miners in config["miners"].

def generate_temp_process_model(xes_path):
    log = xes_importer.apply(xes_path)
    results = {}
    miners_cfg = config.get("miners", {})

    if miners_cfg.get("alpha_miner", False):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            try:
                net, im, fm = alpha_miner.apply(log)
                gviz = pn_visualizer.apply(net, im, fm)
                pn_visualizer.save(gviz, tmp.name)
                results["alpha_miner"] = tmp.name
            except Exception as e:
                print("⚠️ Konnte Alpha-Miner-Modell nicht rendern (Graphviz installiert?).", e)

    if miners_cfg.get("heuristics_miner", False):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            try:
                net, im, fm = heuristics_miner.apply(log)
                gviz = pn_visualizer.apply(net, im, fm)
                pn_visualizer.save(gviz, tmp.name)
                results["heuristics_miner"] = tmp.name
            except Exception as e:
                print("⚠️ Konnte Heuristics-Miner-Modell nicht rendern.", e)

    if miners_cfg.get("inductive_miner", False):
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            try:
                process_tree = inductive_miner.apply(log)
                net, im, fm = pt_converter.apply(process_tree)
                gviz = pn_visualizer.apply(net, im, fm)
                pn_visualizer.save(gviz, tmp.name)
                results["inductive_miner"] = tmp.name
            except Exception as e:
                print("⚠️ Konnte Inductive-Miner-Modell nicht rendern.", e)

    return results

# ========================
# Conformance
# ========================
# Computes standard conformance metrics per miner and returns a mapping that the
# PDF section can render as a small table next to each model image.

def analyze_inductive_miner(log):
    process_tree = inductive_miner.apply(log, variant=inductive_miner.Variants.IMd)
    net, im, fm = pt_converter.apply(process_tree)
    fitness = round(fitness_evaluator.apply(log, net, im, fm)['averageFitness'], 4)
    precision = round(precision_evaluator.apply(log, net, im, fm), 4)
    generalization = round(generalization_evaluator.apply(log, net, im, fm), 4)
    return [("Fitness", fitness), ("Precision", precision), ("Generalization", generalization)]

def analyze_alpha_miner(log):
    net, im, fm = alpha_miner.apply(log)
    fitness = round(fitness_evaluator.apply(log, net, im, fm)['averageFitness'], 4)
    precision = round(precision_evaluator.apply(log, net, im, fm), 4)
    generalization = round(generalization_evaluator.apply(log, net, im, fm), 4)
    return [("Fitness", fitness), ("Precision", precision), ("Generalization", generalization)]

def analyze_heuristics_miner(log):
    heu_net = heuristics_miner.apply_heu(log)
    net, im, fm = hn_converter.apply(heu_net)
    fitness = round(fitness_evaluator.apply(log, net, im, fm)['averageFitness'], 4)
    precision = round(precision_evaluator.apply(log, net, im, fm), 4)
    generalization = round(generalization_evaluator.apply(log, net, im, fm), 4)
    return [("Fitness", fitness), ("Precision", precision), ("Generalization", generalization)]

def analyze_event_log(xes_path):
    log = xes_importer.apply(xes_path)
    results = {}
    miners_cfg = config.get("miners", {})

    if miners_cfg.get("alpha_miner", False):
        results["alpha_miner"] = analyze_alpha_miner(log)
    if miners_cfg.get("heuristics_miner", False):
        results["heuristics_miner"] = analyze_heuristics_miner(log)
    if miners_cfg.get("inductive_miner", False):
        results["inductive_miner"] = analyze_inductive_miner(log)

    return results

# ========================
# PDF generation
# ========================
# Page 1
#   - Title
#   - Grouped findings (Merges, Sequences, Redundancy, Trace Length, Out-of-Gas))
#   - Extra spacing
#   - Summary table
# Following pages
#   - One image per page (charts and process models), with optional metrics table
# Last page (optional)
#   - Reproducibility footnote (runtime + config snapshot)


SEV_ORDER = {"High": 0, "Medium": 1, "Low": 2}
PALETTE = {
    "muted": colors.Color(0.35, 0.38, 0.42),
}

styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontSize=18, textColor=colors.black, spaceAfter=8))
styles.add(ParagraphStyle(name="Subtle", parent=styles["Normal"], fontSize=9, textColor=PALETTE["muted"]))
styles.add(ParagraphStyle(name="Cat", parent=styles["Heading2"], fontSize=13, textColor=colors.black, spaceAfter=4))
styles.add(ParagraphStyle(name="Item", parent=styles["Normal"], fontSize=10, leading=13))

def page_frames_two_cols(doc):
    """Unused helper: create two-column frames if you want a 2-col layout."""
    margin = 18*mm
    gutter = 10*mm
    col_w = (doc.width - gutter) / 2
    left = Frame(doc.leftMargin, doc.bottomMargin, col_w, doc.height, id='left')
    right = Frame(doc.leftMargin + col_w + gutter, doc.bottomMargin, col_w, doc.height, id='right')
    return [left, right]

def title_section():
    """Title + a little breathing room; keep clean (no meta-line)."""
    story = []
    story.append(Paragraph("Optimization Report for XES Analysis", styles["H1"]))
    story.append(Spacer(1, 6))
    return story

# --- PDF: Grouped suggestions (bulleted by category) ---
# Keeps category order stable and prevents orphan bullets via KeepTogether blocks.

def grouped_suggestions_section(grouped, col_width):
    cat_order = [
        ("Merges", "#1B74EE"),
        ("Sequences", "#3EA8D7"),
        ("Redundancy", "#E45D54"),
        ("Trace Length", "#8C7AE6"),
        ("Out-of-Gas", "#4CAF50"),
    ]
    sev_color = {"High": "#D32F2F", "Medium": "#F57C00", "Low": "#2E7D32"}

    story = []

    def build_category_block(cat_name, cat_hex, items_sorted):
        """Chunk large categories to keep KeepTogether realistic on long lists."""
        MAX_ITEMS_PER_BLOCK = 15
        blocks = []
        for start in range(0, len(items_sorted), MAX_ITEMS_PER_BLOCK):
            chunk = items_sorted[start:start + MAX_ITEMS_PER_BLOCK]
            cat_story = []
            if start == 0:
                cat_story.append(Paragraph(f'<font color="{cat_hex}"><b>{cat_name}</b></font>', styles["Cat"]))
                cat_story.append(Spacer(1, 2))
            for it in chunk:
                sev_lbl = {"High": "[HIGH]", "Medium": "[MEDIUM]", "Low": "[LOW]"}[it["sev"]]
                sev_hex = sev_color[it["sev"]]
                p = Paragraph(f'• <font color="{sev_hex}"><b>{sev_lbl}</b></font> {it["text"]}', styles["Item"])
                cat_story.append(p)
                cat_story.append(Spacer(1, 2))
            cat_story.append(Spacer(1, 6))
            blocks.append(KeepTogether(cat_story))
        return blocks

    for cat, cat_hex in cat_order:
        items = grouped.get(cat, [])
        if not items:
            continue
        items_sorted = sorted(items, key=lambda x: (SEV_ORDER.get(x["sev"], 9), -x["count"], x["text"]))
        story.extend(build_category_block(cat, cat_hex, items_sorted))

    return story

# --- PDF: Summary table ---

def summary_section(summary_dict):
    story = [Paragraph("Summary", styles["H1"])]
    data = [["Metric", "Value"]] + [[str(k), str(v)] for k, v in summary_dict.items()]
    table = Table(data, colWidths=[80*mm, 90*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.Color(0.95, 0.95, 0.97)]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.84, 0.87, 0.92)),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(table)
    story.append(Spacer(1, 8))
    return story

# --- PDF: Image embedding (charts + models) ---

def fitted_image(path, max_w, max_h):
    """Scale an image to fit inside (max_w, max_h) preserving aspect ratio."""
    with Image.open(path) as im:
        w, h = im.size
    if w == 0 or h == 0:
        return RLImage(path, width=max_w, height=max_h * 0.6)
    aspect = h / float(w)
    tgt_w = min(max_w, w)
    tgt_h = tgt_w * aspect
    if tgt_h > max_h:
        tgt_h = max_h
        tgt_w = tgt_h / aspect
    return RLImage(path, width=tgt_w, height=tgt_h)

def images_section(image_paths, doc_width, doc_height, metrics=None):
    """One image per page. Optionally displays a small metric table under it.

    image_paths: dict like {"redundant": "/tmp/..png", "inductive_miner": "/tmp/..png", ...}
    metrics: dict like {"inductive_miner": [("Fitness", 0.98), ...], ...}
    """
    story = []
    from reportlab.platypus import PageBreak

    IMG_MAX_WIDTH = doc_width
    IMG_MAX_HEIGHT = doc_height * 0.62  # leave space for title + metrics

    for title, img_path in image_paths.items():
        if not os.path.exists(img_path):
            continue

        story.append(PageBreak())
        story.append(Paragraph(title, styles["Cat"]))
        story.append(Spacer(1, 8))

        try:
            img = fitted_image(img_path, IMG_MAX_WIDTH, IMG_MAX_HEIGHT)
            img.hAlign = 'CENTER'
            story.append(img)
        except Exception as e:
            story.append(Paragraph(f"[Image could not be embedded: {e}]", styles["Subtle"]))

        if metrics and title in metrics:
            m = metrics[title]
            m_data = [["Metric", "Value"]] + [[a, str(b)] for a, b in m]
            mt = Table(m_data, colWidths=[60*mm, 40*mm])
            mt.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.Color(0.84, 0.87, 0.92)),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(Spacer(1, 10))
            story.append(mt)

        story.append(Spacer(1, 6))

    return story

# --- PDF: Footnote with parameters for reproducibility ---

def footnote_section(text):
    story = []
    if not text:
        return story
    story.append(Paragraph("Parameter footnote (reproducibility)", styles["H1"]))
    mono = ParagraphStyle(name="mono", parent=styles["Normal"], fontName="Helvetica", fontSize=8, leading=10)
    for line in text.splitlines():
        story.append(Paragraph(line.replace(" ", "&nbsp;"), mono))
    return story

# --- PDF: Build document from sections ---

def save_to_pdf(pdf_path, grouped_suggestions, summary_dict, image_paths, metrics=None, parameter_footnote=None):
    from reportlab.platypus import PageBreak, Spacer
    doc = SimpleDocTemplate(
        pdf_path, pagesize=A4,
        rightMargin=18*mm, leftMargin=18*mm, topMargin=16*mm, bottomMargin=16*mm
    )

    # Current design: single-column for stability with long lists
    frame_one = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id='one')
    tmpl_one = PageTemplate(id='one_col', frames=[frame_one])
    doc.addPageTemplates([tmpl_one])

    story = []

    # Page 1 – Title + grouped categories
    story.extend(title_section())
    story.extend(grouped_suggestions_section(grouped_suggestions, col_width=doc.width))

    # Extra spacing before summary (keeps summary on page 1 when possible)
    story.append(Spacer(1, 20))

    # Summary on same page if space permits
    story.extend(summary_section(summary_dict))

    # Images & models – one per page
    story.extend(images_section(image_paths, doc_width=doc.width, doc_height=doc.height, metrics=metrics))

    # Optional final page with parameter snapshot
    if parameter_footnote:
        story.append(PageBreak())
        story.extend(footnote_section(parameter_footnote))

    doc.build(story)

    # Cleanup temp images (ignore if files are locked on some OSes)
    for path in image_paths.values():
        try:
            if os.path.exists(path):
                os.remove(path)
        except PermissionError:
            print(f"⚠️ Warning: could not delete file: {path}")

# ========================
# Main
# ========================

if __name__ == "__main__":
    if not os.path.exists(LOG_FILE_PATH):
        print(f"❌ XES file not found: {LOG_FILE_PATH}")
        sys.exit(1)

    print("🔍 Analyzing XES...")
    grouped, summary, chart_paths, meta = generate_analysis_and_charts(LOG_FILE_PATH)

    print("📈 Generating temporary process model...")
    model_img_paths = generate_temp_process_model(LOG_FILE_PATH)
    chart_paths.update(model_img_paths)

    print("📊 Computing metrics...")
    metrics = analyze_event_log(LOG_FILE_PATH)

    print("🧪 Collecting runtime context & parameter snapshot...")
    runtime_ctx = get_runtime_context()
    param_text = build_param_snapshot(config=config, meta=meta, runtime_ctx=runtime_ctx)

    print("📝 Creating PDF...")
    save_to_pdf(
        PDF_OUTPUT_PATH,
        grouped_suggestions=grouped,
        summary_dict=summary,
        image_paths=chart_paths,
        metrics=metrics,
        parameter_footnote=param_text
    )

    print(f"✅ Done! PDF saved at:\n{PDF_OUTPUT_PATH}")
