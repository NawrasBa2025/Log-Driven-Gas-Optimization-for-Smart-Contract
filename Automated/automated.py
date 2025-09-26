import os
import xml.etree.ElementTree as ET
from datetime import datetime
from collections import defaultdict
import yaml
import json
import numpy as np
import json
import pandas as pd

CONFIG_PATH = "automated-config.yaml"

def load_config(config_path):
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def parse_timestamp(ts):
    if not ts:
        return None
    ts = str(ts).strip().replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(ts)
    except:
        return None

def generate_analysis(file_path, run_name, TIME_THRESHOLD_SECONDS, MAX_L, PERCENTILE,
                      features, keys, maximal_sequence_suggestion=None,
                      fallback_user=True, trace_user_attr="concept:name"):
    tree = ET.parse(file_path)
    root = tree.getroot()
    traces = root.findall('.//trace')

    raw_merge_suggestions = defaultdict(int)
    redundant = defaultdict(int)
    sequences = defaultdict(int)
    trace_lengths = []
    trace_groups = defaultdict(list)
    trace_user_fallback = {}

    # Collect events for each trace with a fallback user (from trace attributes) if needed
    for idx, trace in enumerate(traces):
        trace_attrs = {child.attrib.get('key'): child.attrib.get('value') for child in trace if child.tag != 'event'}
        fb_user = trace_attrs.get(trace_user_attr) if fallback_user else None
        trace_user_fallback[idx] = fb_user or f"trace_{idx}"
        for event in trace.findall('event'):
            evt_data = {child.attrib.get('key'): child.attrib.get('value') for child in event}
            trace_groups[idx].append(evt_data)

    # Analyze each trace
    for trace_idx, events in trace_groups.items():
        trace_lengths.append(len(events))
        user_event_map = defaultdict(list)
        fb_user = trace_user_fallback.get(trace_idx)

        for evt_data in events:
            user = evt_data.get(keys["USER_KEY"]) or fb_user
            user_event_map[user].append(evt_data)

        for user, user_events in user_event_map.items():
            user_events.sort(key=lambda x: parse_timestamp(x.get(keys["TIMESTAMP_KEY"])))
            prev_event = None
            activity_list = []
            timestamp_list = []

            for e in user_events:
                activity = e.get(keys["ACTIVITY_KEY"])
                timestamp = parse_timestamp(e.get(keys["TIMESTAMP_KEY"]))
                if prev_event:
                    prev_activity = prev_event.get(keys["ACTIVITY_KEY"])
                    prev_timestamp = parse_timestamp(prev_event.get(keys["TIMESTAMP_KEY"]))

                    # Redundancy: same activity performed consecutively by the same user
                    if activity == prev_activity and features.get('redundancy', True):
                        redundant[activity] += 1

                    # Merge: two consecutive events within the configured time threshold
                    if prev_timestamp and timestamp and 0 < (timestamp - prev_timestamp).total_seconds() <= TIME_THRESHOLD_SECONDS:
                        if features.get('merge', True):
                            raw_merge_suggestions[(prev_activity, activity)] += 1

                activity_list.append(activity)
                timestamp_list.append(timestamp)
                prev_event = e

            # Sequence detection: sliding windows up to MAX_L within the time threshold
            n = len(activity_list)
            for window_size in range(3, min(n, MAX_L) + 1):
                for i in range(n - window_size + 1):
                    window_timestamps = timestamp_list[i:i + window_size]
                    if (
                        window_timestamps[0] is not None and
                        window_timestamps[-1] is not None and
                        0 < (window_timestamps[-1] - window_timestamps[0]).total_seconds() <= TIME_THRESHOLD_SECONDS and
                        features.get('sequence', True)
                    ):
                        sequence_tuple = tuple(activity_list[i:i + window_size])
                        sequences[sequence_tuple] += 1

    # Longest trace length (by number of events)
    max_trace_length = max(trace_lengths) if trace_lengths else 0

    # Percentile statistics on trace lengths
    pctl_threshold = int(np.percentile(trace_lengths, PERCENTILE)) if trace_lengths else None
    long_traces_above = sum(1 for L in trace_lengths if (pctl_threshold is not None and L > pctl_threshold)) if trace_lengths else 0

    # Count qualifying sequences (those appearing at least twice); cap by maximal_sequence_suggestion if provided
    sequenzen_count = len([1 for _, count in sequences.items() if count >= 2])
    if maximal_sequence_suggestion is not None:
        sequenzen_count = min(sequenzen_count, maximal_sequence_suggestion)

    result = {
        "Run": run_name,
        "TIME (s)": TIME_THRESHOLD_SECONDS,
        "MAX_SEQ_LEN": MAX_L,
        "Merges": sum(raw_merge_suggestions.values()),
        "Sequenzen": sequenzen_count,
        "PERCENTILE": PERCENTILE,
        "Long_Traces": long_traces_above
        # "Pctl_Threshold": pctl_threshold,
        # "Redundancies": sum(redundant.values()),
        # "Trace-Length": max_trace_length
    }

    return result


if __name__ == "__main__":
    config = load_config(CONFIG_PATH)
    LOG_FILE_PATH = config.get("LOG_FILE_PATH", "./Augur.xes")
    OUTPUT_NAME = config.get("OUTPUT_NAME", "analysis_summary.json")
    PERCENTILE_DEFAULT = config.get("PERCENTILE", 99)
    features = config.get("features", {})
    keys = {
        "TIMESTAMP_KEY": config.get("TIMESTAMP_KEY", "time:timestamp"),
        "ACTIVITY_KEY": config.get("ACTIVITY_KEY", "concept:name"),
        "USER_KEY": config.get("USER_KEY", "org:resource")
    }
    maximal_sequence_suggestion = config.get("maximal_sequence_suggestion", 10000)
    fallback_user = config.get("FALLBACK_USER_FROM_TRACE", True)
    trace_user_attr = config.get("TRACE_USER_ATTR", "concept:name")

    all_results = []

    for run in config.get("runs", []):
        run_name = run.get("name", "R?")
        TIME_THRESHOLD_SECONDS = run.get("TIME_THRESHOLD_SECONDS", 60)
        MAX_L = run.get("MAX_SEQUENCE_LENGTH", 5)
        PERCENTILE = run.get("PERCENTILE", PERCENTILE_DEFAULT)

        print(f"▶️ Running {run_name} ...")
        summary = generate_analysis(
            LOG_FILE_PATH, run_name, TIME_THRESHOLD_SECONDS, MAX_L, PERCENTILE,
            features, keys, maximal_sequence_suggestion,
            fallback_user=fallback_user, trace_user_attr=trace_user_attr
        )
        all_results.append(summary)

    output_path = OUTPUT_NAME
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"✅ Saved {len(all_results)} results into {output_path}")

    with open(OUTPUT_NAME, "r", encoding="utf-8") as f:
        data = json.load(f)

        # Convert results to a DataFrame
        df = pd.DataFrame(data)

        # Print the table to stdout
        print(df)
