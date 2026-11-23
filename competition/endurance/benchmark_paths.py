"""Compare reusable A* to the frozen implementation, including graph build.

Run from learn: .venv/bin/python -m competition.endurance.benchmark_paths
The 18 fixed maps are not filtered by reachability or relative performance.
Single-query, all-pairs and repeated-cache timings are reported separately.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import random
import signal
import statistics
import time

from competition.core import planning as legacy
from . import pathfinding


def timed(call):
    started = time.perf_counter()
    result = call()
    return result, (time.perf_counter() - started) * 1000.0


def compare(first, second):
    return (first["status"] == second["status"]
            and (first["status"] != "planned" or abs(first["cost"] - second["cost"]) <= 1e-7))


def scenarios():
    for size in (16, 32, 64):
        for density in (0.0, .1, .2):
            for replicate in range(2):
                seed = 20261116 + size * 100 + round(density * 100) + replicate
                rng = random.Random(seed)
                blocked = {(x, y) for x in range(size) for y in range(size)
                           if rng.random() < density} - {(0, 0), (size - 1, size - 1)}
                nodes = [(0, 0), (size - 1, size - 1)]
                free = [(x, y) for x in range(size) for y in range(size)
                        if (x, y) not in blocked and (x, y) not in nodes]
                nodes.extend(rng.sample(free, 6))
                winds = [] if replicate == 0 else [
                    dict(x_min=0, x_max=size - 1, y_min=0, y_max=size - 1, vector=[2., -.75]),
                    dict(x_min=size // 3, x_max=2 * size // 3, y_min=0,
                         y_max=size - 1, vector=[-3., 1.5])]
                yield dict(size=size, density=density, seed=seed,
                           blocked=sorted(blocked), wind_regions=winds, nodes=nodes)


def run_case(scene, objective):
    size, blocked, winds = scene["size"], scene["blocked"], scene["wind_regions"]
    nodes = scene["nodes"]

    def original(a, b):
        return legacy.plan(a, b, size, size, blocked, winds, 10.0, objective)

    def graph():
        return pathfinding.GridPlanner(size, size, blocked, winds, 10.0)

    # A fresh context in each repetition includes the one-off construction cost.
    singles = []
    for _ in range(3):
        old, old_ms = timed(lambda: original(nodes[0], nodes[1]))
        context, build_ms = timed(graph)
        new, query_ms = timed(lambda: context.plan(nodes[0], nodes[1], objective))
        singles.append(dict(legacy_ms=old_ms, build_ms=build_ms, query_ms=query_ms,
                            optimized_total_ms=build_ms + query_ms,
                            equivalent_cost=compare(old, new),
                            legacy_expanded=old["expanded_nodes"],
                            optimized_expanded=new["expanded_nodes"]))

    queries = []
    context, build_ms = timed(graph)
    for a in nodes:
        for b in nodes:
            if a == b:
                continue
            old, old_ms = timed(lambda: original(a, b))
            new, new_ms = timed(lambda: context.plan(a, b, objective))
            queries.append(dict(start=a, goal=b, status=old["status"],
                                legacy_cost=old.get("cost"), optimized_cost=new.get("cost"),
                                equivalent_cost=compare(old, new),
                                legacy_ms=old_ms, optimized_query_ms=new_ms,
                                legacy_expanded=old["expanded_nodes"],
                                optimized_expanded=new["expanded_nodes"]))
    cached_queries = []
    for row in queries:
        result, elapsed = timed(lambda: context.plan(row["start"], row["goal"], objective))
        cached_queries.append(dict(query_ms=elapsed, cache_hit=result["cache_hit"],
                                   expanded_nodes=result["expanded_nodes"]))
    old_many = sum(r["legacy_ms"] for r in queries)
    new_many = build_ms + sum(r["optimized_query_ms"] for r in queries)
    return dict(map={**scene, "blocked": [list(p) for p in blocked]}, objective=objective,
                single_query_repetitions=singles,
                single_legacy_median_ms=statistics.median(r["legacy_ms"] for r in singles),
                single_optimized_median_ms=statistics.median(r["optimized_total_ms"] for r in singles),
                multi_build_ms=build_ms, multi_legacy_total_ms=old_many,
                multi_optimized_total_ms=new_many,
                multi_speedup_including_build=old_many / new_many,
                cache_repeat_total_ms=sum(r["query_ms"] for r in cached_queries),
                cache_hits=sum(r["cache_hit"] for r in cached_queries),
                edge_model_calls=context.edge_model_calls,
                directed_edges=context.edge_count, queries=queries)


def summarize(cases):
    summaries = []
    for objective in ("energy", "distance"):
        rows = [row for row in cases if row["objective"] == objective]
        if not rows:
            continue
        old_single = sum(row["single_legacy_median_ms"] for row in rows)
        new_single = sum(row["single_optimized_median_ms"] for row in rows)
        old_many = sum(row["multi_legacy_total_ms"] for row in rows)
        new_many = sum(row["multi_optimized_total_ms"] for row in rows)
        old_expanded = sum(q["legacy_expanded"] for row in rows for q in row["queries"])
        new_expanded = sum(q["optimized_expanded"] for row in rows for q in row["queries"])
        summaries.append(dict(
            objective=objective, map_count=len(rows), queries=sum(len(row["queries"]) for row in rows),
            single_query_legacy_sum_ms=old_single, single_query_optimized_sum_ms=new_single,
            single_query_speedup_including_build=old_single / new_single,
            multi_query_legacy_total_ms=old_many, multi_query_optimized_total_ms=new_many,
            multi_query_speedup_including_build=old_many / new_many,
            faster_multi_cases=sum(row["multi_optimized_total_ms"] < row["multi_legacy_total_ms"] for row in rows),
            slower_or_equal_multi_cases=sum(row["multi_optimized_total_ms"] >= row["multi_legacy_total_ms"] for row in rows),
            cached_repeat_total_ms=sum(row["cache_repeat_total_ms"] for row in rows),
            legacy_expanded_nodes=old_expanded, optimized_expanded_nodes=new_expanded,
            expansion_reduction_fraction=1 - new_expanded / old_expanded))
    return summaries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent / "evidence" / "astar-benchmark.json")
    parser.add_argument("--timeout", type=int, default=60)
    args = parser.parse_args()
    if args.timeout <= 0:
        parser.error("timeout must be positive")

    def timeout(_signal, _frame):
        raise TimeoutError("benchmark exceeded hard timeout")

    signal.signal(signal.SIGALRM, timeout)
    signal.alarm(args.timeout)
    started = time.perf_counter()
    cases = []
    status, error = "completed", None
    try:
        # Import/warmup happens before recorded cases, identically for both codes.
        legacy.plan((0, 0), (3, 3), 4, 4, [], [], 10.)
        pathfinding.GridPlanner(4, 4, [], []).plan((0, 0), (3, 3))
        for scene in scenarios():
            for objective in ("energy", "distance"):
                result = run_case(scene, objective)
                cases.append(result)
                print(f"{len(cases):02}/36 size={scene['size']} density={scene['density']:.1f} "
                      f"objective={objective} speedup_with_build={result['multi_speedup_including_build']:.3f}", flush=True)
    except TimeoutError as exc:
        status, error = "timed_out", str(exc)
    finally:
        signal.alarm(0)
    evidence = dict(
        schema_version=1, captured_at=datetime.now(timezone.utc).isoformat(), status=status, error=error,
        scope="software performance on 18 fixed synthetic grids; not an aircraft performance experiment",
        settings=dict(sizes=[16, 32, 64], obstacle_densities=[0, .1, .2], maps=18,
                      objectives=["energy", "distance"], points_per_map=8, directed_queries_per_map=56,
                      single_query_repetitions=3, timeout_seconds=args.timeout,
                      airspeed_ms=5., power_w=legacy.UPPER_POWER_W, cell_size_m=10.),
        python=platform.python_version(), system=platform.platform(), elapsed_s=time.perf_counter() - started,
        source_sha256={str(Path(module.__file__).relative_to(Path(__file__).resolve().parents[2])):
                       hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
                       for module in (legacy, pathfinding)},
        all_costs_equivalent=all(q["equivalent_cost"] for row in cases for q in row["queries"])
                             and all(q["equivalent_cost"] for row in cases for q in row["single_query_repetitions"]),
        summary=summarize(cases), cases=cases)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: evidence[key] for key in ("status", "elapsed_s", "all_costs_equivalent", "summary")}, indent=2))
    if status != "completed" or not evidence["all_costs_equivalent"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
