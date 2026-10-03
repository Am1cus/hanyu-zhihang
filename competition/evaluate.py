"""Bounded offline paired evaluations; no wall-clock waits or old project DB."""
from __future__ import annotations

import argparse
import csv
import json
import math
import platform
from pathlib import Path

from .core.curves import CurveLibrary, DEFAULT_PATH
from .core.scenarios import formal_manifest
from .core.simulator import MissionRun, compare_runs


def timing_summary(metrics):
    def distribution(key):
        values = sorted(row[key] for row in metrics if row.get(key) is not None)
        def quantile(p):
            return values[max(0, math.ceil(p * len(values)) - 1)] if values else None
        return {"count": len(values), "mean": sum(values) / len(values) if values else None,
                "p50": quantile(.5), "p95": quantile(.95), "p99": quantile(.99), "max": values[-1] if values else None}
    return {"event_compute_ms": distribution("event_compute_ms"),
            "decision_compute_ms": distribution("decision_compute_ms"),
            "simulated_reaction_s": distribution("simulated_reaction_s"),
            "boundary": "local_python_event_and_planning_cpu; simulation_seconds_to_next_decision; excludes_browser_network_and_playback_speed",
            "host": {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version()}}


def run_all(curve_path=DEFAULT_PATH, reserve_fraction=.2, output_dir=None,
            load_mismatch_fraction=0, wind_observation_bias_ms=0, sensitivity_family=None):
    library = CurveLibrary(curve_path)
    manifest = formal_manifest()
    results, rows, exports, timings = [], [], [], []
    for case in manifest["cases"]:
        pair = [MissionRun({"scenario_id": case["scenario_id"], "temperature_c": case["temperature_c"],
                            "strategy": strategy, "reserve_fraction": reserve_fraction,
                            "load_mismatch_fraction": load_mismatch_fraction,
                            "wind_observation_bias_ms": wind_observation_bias_ms}, library).run_all()
                for strategy in ("distance", "energy")]
        result = {"scenario_id": case["scenario_id"], "temperature_c": case["temperature_c"],
                  "distance": pair[0].summary(), "energy": pair[1].summary(), "comparison": compare_runs(*pair)}
        results.append(result)
        for run in pair:
            rows.append({"scenario_id": case["scenario_id"], "temperature_c": case["temperature_c"],
                         "strategy": run.strategy, "status": run.status, **run.summary()})
            exports.append(run.export())
            timings.extend(run.response_metrics)
    comparable = [r["comparison"]["energy_saving_pct"] for r in results if r["comparison"]["status"] == "comparable"]
    report = {"schema_version": 1, "data_source": "LOCAL_2D_SIM", "curve_status": library.status(),
              "formal": reserve_fraction == .2 and load_mismatch_fraction == 0 and wind_observation_bias_ms == 0 and sensitivity_family is None,
              "reserve_fraction": reserve_fraction,
              "experiment": {"sensitivity_family": sensitivity_family,
                             "load_mismatch_fraction": load_mismatch_fraction,
                             "execution_current_a": library.current_a,
                             "estimated_current_a": library.current_a / (1 + load_mismatch_fraction),
                             "wind_observation_bias_x_ms": wind_observation_bias_ms,
                             "load_bias_definition": "actual_execution_current_divided_by_estimated_current_minus_one; execution_remains_4.2A_reference_condition",
                             "wind_bias_definition": "planner_observed_x_component_minus_executor_true_x_component; other_components_unchanged"},
              "manifest": manifest, "cases": results,
              "aggregate": {"scenario_count": len(results), "execution_count": len(rows),
                            "failed_or_unavailable_executions": sum(r["status"] in ("FAILED", "UNAVAILABLE") for r in rows),
                            "returned_executions": sum(r["returned"] for r in rows),
                            "full_task_executions": sum(r["mission_completion_ratio"] == 1 for r in rows),
                            "comparable_pairs": len(comparable),
                            "mean_energy_saving_pct_comparable_only": sum(comparable) / len(comparable) if comparable else None,
                            "real_flights": 0},
              "limitation": "Manufacturer cell reference curves and synthetic software scenarios; no real aircraft savings or safety claim."}
    report["response_timings"] = timing_summary(timings)
    if output_dir:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        (out / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        with (out / "runs.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        archive = out / "runs"
        archive.mkdir(exist_ok=True)
        for export in exports:
            config = export["configuration"]
            name = f"{config['scenario_id']}-t{config['temperature_c']:g}-{config['strategy']}.json"
            (archive / name).write_text(json.dumps(export, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curves", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--reserve-fraction", type=float, default=.2)
    parser.add_argument("--sensitivity", action="store_true", help="separate reserve/load/wind-observation one-factor-at-a-time runs")
    arguments = parser.parse_args()
    if arguments.sensitivity:
        reports = [run_all(arguments.curves, fraction, arguments.output / f"reserve-{fraction:.2f}", sensitivity_family="reserve") for fraction in (.1, .2, .3)]
        reports += [run_all(arguments.curves, .2, arguments.output / f"load-{bias:+.2f}", load_mismatch_fraction=bias,
                            sensitivity_family="load_mismatch") for bias in (-.1, .1)]
        reports += [run_all(arguments.curves, .2, arguments.output / f"wind-{bias:+.2f}", wind_observation_bias_ms=bias,
                            sensitivity_family="wind_observation") for bias in (-.5, .5)]
        print(json.dumps({"sensitivity_only": True, "aggregates": [r["aggregate"] for r in reports]}, ensure_ascii=False))
    else:
        report = run_all(arguments.curves, arguments.reserve_fraction, arguments.output)
        print(json.dumps(report["aggregate"], ensure_ascii=False))


if __name__ == "__main__":
    main()
