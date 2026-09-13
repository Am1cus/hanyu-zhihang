"""Offline, per-run voltage threshold labels and event lead-time evaluation."""
import argparse
import json
import math
from pathlib import Path


def evaluate(rows, threshold_v, horizon_s, step_s=1.0):
    """Rows: run_id, t_s, voltage_v (nullable), risk (bool or null).

    Label uses (t, t+horizon], only complete contiguous voltage observations.
    Event = first <= threshold after an observed > threshold sample.
    Full horizon of preceding observations is required for event eligibility.
    """
    for value in (threshold_v, horizon_s, step_s):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError("threshold, horizon and step must be finite and positive")
    steps = round(horizon_s / step_s)
    if steps < 1 or not math.isclose(steps * step_s, horizon_s, abs_tol=1e-8):
        raise ValueError("horizon must be a positive multiple of step")
    groups = {}
    for row in rows:
        run = row["run_id"]
        if not isinstance(run, str) or not run:
            raise ValueError("run_id required")
        t = row["t_s"]
        if isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) or t < 0:
            raise ValueError("invalid source time")
        v = row.get("voltage_v")
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v <= 0):
            raise ValueError("voltage must be positive or null")
        if row.get("risk") is not None and type(row["risk"]) is not bool:
            raise ValueError("risk must be boolean or null")
        groups.setdefault(run, []).append(row)
    per_run = []
    labels, events = [], []
    total = dict(tp=0, fp=0, tn=0, fn=0, abstained=0, unlabelled=0, active=0,
                 eligible_events=0, detected_events=0, censored_onsets=0)
    for run, samples in groups.items():
        samples.sort(key=lambda r: r["t_s"])
        if len({r["t_s"] for r in samples}) != len(samples):
            raise ValueError("duplicate timestamps within run")
        counts = dict.fromkeys(total, 0)
        segments, segment = [], []
        for row in samples:
            if row.get("voltage_v") is None or (segment and not math.isclose(row["t_s"]-segment[-1]["t_s"], step_s, abs_tol=1e-8)):
                if segment:
                    segments.append(segment)
                segment = []
            if row.get("voltage_v") is None:
                counts["unlabelled"] += 1
                labels.append({"run_id": run, "t_s": row["t_s"], "label": None, "reason": "missing_voltage"})
            else:
                segment.append(row)
        if segment:
            segments.append(segment)
        for seq in segments:
            last_low = -1
            if seq[0]["voltage_v"] <= threshold_v:
                counts["censored_onsets"] += 1
            for i, row in enumerate(seq):
                active = row["voltage_v"] <= threshold_v
                previous_low = last_low
                if active:
                    last_low = i
                if active:
                    counts["active"] += 1
                    labels.append({"run_id": run, "t_s": row["t_s"], "label": None, "reason": "already_below_threshold"})
                elif i + steps >= len(seq):
                    counts["unlabelled"] += 1
                    labels.append({"run_id": run, "t_s": row["t_s"], "label": None, "reason": "incomplete_future"})
                else:
                    label = any(s["voltage_v"] <= threshold_v for s in seq[i+1:i+steps+1])
                    risk = row.get("risk")
                    outcome = "abstained" if risk is None else (("tp" if risk else "fn") if label else ("fp" if risk else "tn"))
                    counts[outcome] += 1
                    labels.append({"run_id": run, "t_s": row["t_s"], "label": label, "risk": risk})
                if not active or i == 0 or seq[i-1]["voltage_v"] <= threshold_v:
                    continue
                # Events without a complete pre-event observation window stay censored.
                eligible = i >= steps
                alarms = [s["t_s"] for s in seq[max(0,i-steps,previous_low+1):i]
                          if s["voltage_v"] > threshold_v and s.get("risk") is True]
                lead = row["t_s"] - min(alarms) if eligible and alarms else None
                counts["eligible_events" if eligible else "censored_onsets"] += 1
                if lead is not None:
                    counts["detected_events"] += 1
                events.append({"run_id": run, "event_t_s": row["t_s"], "eligible": eligible,
                               "lead_s": lead, "detected": lead is not None})
        per_run.append({"run_id": run, **counts})
        for key in total:
            total[key] += counts[key]
    def ratio(a, b):
        return a / b if b else None
    return {"schema_version": 1, "threshold_v": threshold_v, "horizon_s": horizon_s,
            "counts": total, "per_run": per_run, "labels": labels, "events": events,
            "sample_precision": ratio(total["tp"], total["tp"]+total["fp"]),
            "sample_recall_available": ratio(total["tp"], total["tp"]+total["fn"]),
            "prediction_coverage": ratio(sum(total[k] for k in ("tp","fp","tn","fn")), sum(total[k] for k in ("tp","fp","tn","fn","abstained"))),
            "event_recall": ratio(total["detected_events"], total["eligible_events"]),
            "missed_events": total["eligible_events"]-total["detected_events"],
            "scope": "offline_evaluator_not_a_predictive_model",
            "sample_unit": "overlapping_time_points_not_independent_flights"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--threshold-v", required=True, type=float)
    parser.add_argument("--horizon-s", required=True, type=float)
    parser.add_argument("--step-s", type=float, default=1)
    args = parser.parse_args()
    print(json.dumps(evaluate(json.loads(args.input.read_text()), args.threshold_v, args.horizon_s, args.step_s), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
