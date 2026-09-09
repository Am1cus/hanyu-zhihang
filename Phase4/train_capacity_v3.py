"""Three-stage locked experiment: prepare -> fit -> evaluate (no deployed writes).

All tuning uses development flights. Evaluation refuses a changed protocol,
source ZIP, or implementation and writes a one-shot test marker before testing.
"""
from __future__ import annotations

import argparse
import copy
import json
import platform
import random
import time
from pathlib import Path

import joblib
import numpy as np
import sklearn
import torch
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from torch.utils.data import DataLoader, TensorDataset

from capacity_v3 import (ALL_FEATURES, FEATURE_SETS, FULL, EnergyLSTM, build_windows,
                         causal_baselines, group_metrics, predict_network, read_dataset,
                         selected_features, sha256, subset, tabular_features, write_json)

CONFIGS = [
    {"name": "residual_core32", "features": "core", "hidden": 32, "residual": True},
    {"name": "residual_full16", "features": "full", "hidden": 16, "residual": True},
    {"name": "residual_full32", "features": "full", "hidden": 32, "residual": True},
    {"name": "residual_full64", "features": "full", "hidden": 64, "residual": True},
    {"name": "residual_no_thermal32", "features": "no_thermal", "hidden": 32, "residual": True},
    {"name": "residual_with_altitude32", "features": "with_altitude", "hidden": 32, "residual": True},
    {"name": "direct_full32", "features": "full", "hidden": 32, "residual": False},
    {"name": "residual_current_only16", "features": "current_only", "hidden": 16, "residual": True},
]
SEEDS = [17, 42, 2026]


def implementation_hashes():
    return {p.name: sha256(p) for p in (Path(__file__), Path(__file__).with_name("capacity_v3.py"))}


def check_protocol(out):
    p = out/"protocol.json"
    protocol = json.loads(p.read_text())
    lock = json.loads((out/"protocol_lock.json").read_text())
    if sha256(p) != lock["protocol_sha256"] or implementation_hashes() != protocol["implementation"]:
        raise ValueError("Protocol/implementation changed: create a separate experiment, do not reuse test")
    if sha256(protocol["source"]) != protocol["source_sha256"]:
        raise ValueError("Source ZIP changed")
    return protocol


def prepare(source, out):
    out.mkdir(parents=True, exist_ok=False)
    frames, meta, excluded = read_dataset(source)
    splits = {s: sorted(f for f, m in meta.items() if m["split"]==s)
              for s in ("train", "val", "test", "extra")}
    assert len(set(sum(splits.values(), []))) == sum(map(len, splits.values()))
    # Predeclared representative inner holdouts add climb/dynamic validation.
    inner = ["F008", "F010"]
    fit = [f for f in splits["train"] if f not in inner]
    validation = sorted(splits["val"] + inner)
    protocol = {
        "experiment": "capacity_v3_dataset_v2_20260908", "created_local": time.strftime("%Y-%m-%d %H:%M:%S%z"),
        "source": str(source.resolve()), "source_sha256": sha256(source),
        "implementation": implementation_hashes(), "splits": splits,
        "development_fit": fit, "development_validation": validation,
        "excluded": excluded, "metadata": meta,
        "target": "mean_charge(t)-mean_charge(t+10), Ah; 30 complete 1Hz input bins",
        "availability": "[k,k+1) bin emitted at k+1; discard incomplete terminal bin; no interpolation",
        "excluded_inputs": ["flight_id", "absolute_time", "termination_time", "future_current", "phase", "position", "available_capacity_ah"],
        "seeds": SEEDS, "configs": CONFIGS, "epochs_max": 120, "patience": 20,
        "lr": 0.002, "weight_decay": 0.0001, "batch_size": 128, "train_stride": 2,
        "selection": "minimum seed-mean development flight-macro MAPE; never test or extra",
        "final_fit": "original 10 eligible train flights only, same 3 seeds; fixed median best development epoch; arithmetic mean of 3 predictions",
        "baseline_search": {"ridge_alpha": [1, 10, 100], "tree_leaves": [7, 15], "tree_iterations": [60, 120]},
        "reporting": "all fixed candidates, seed results, per-flight and nonoverlap metrics; no seed or test-flight cherry-picking",
        "prior_test_exposure": "dataset audited and legacy V2 evaluated previously; these are held-out V3 development flights, NOT a pristine new confirmation dataset",
        "promotion_gate": "selected LSTM beats validation-selected non-neural comparator and history_10s by >=10% relative macro-MAPE on BOTH test and extra, wins >=2/3 test and >=3/4 extra flights, all 3 seeds beat comparator group macro, positive finite outputs; no automatic online deployment",
        "limitations": "simulation kinematics + formula battery; only 3 main test flights and 4 supplementary flights; fresh-seed confirmation and real battery validation needed",
        "runtime": {"python": platform.python_version(), "torch": torch.__version__, "sklearn": sklearn.__version__, "platform": platform.platform()},
    }
    write_json(out/"protocol.json", protocol)
    write_json(out/"protocol_lock.json", {"protocol_sha256": sha256(out/"protocol.json")})
    counts = {s: {"flights": ids, "windows": len(build_windows(frames, ids)["y"])} for s, ids in splits.items()}
    write_json(out/"sample_counts.json", counts)
    print(json.dumps({"prepared": str(out), "splits": counts, "development_fit": fit,
                      "development_validation": validation}, ensure_ascii=False), flush=True)


def fit_scaler(frames, ids, features):
    # Unique observed train seconds, not validation/test nor overlapping windows.
    rows = np.concatenate([frames[f][FEATURE_SETS[features]].dropna().to_numpy() for f in ids])
    return StandardScaler().fit(rows)


def train_network(train, val, scaler, config, seed, protocol, fixed_epochs=None):
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    torch.set_num_threads(1)
    x = selected_features(train["x"], config["features"])
    x = scaler.transform(x.reshape(-1,x.shape[-1])).reshape(x.shape).astype(np.float32)
    reference = float(np.exp(np.log(train["y"]).mean()))
    base = train["base"] if config["residual"] else np.full(len(x), reference)
    # Stride is separately anchored in each flight, not in pooled rows.
    indices = np.concatenate([np.flatnonzero(train["flight"]==f)[::protocol["train_stride"]]
                              for f in np.unique(train["flight"])])
    # Equal contribution per flight despite different recording lengths.
    weights = np.asarray([1/np.sum(train["flight"][indices]==f) for f in train["flight"][indices]])
    weights = weights/weights.mean()
    loader = DataLoader(TensorDataset(torch.tensor(x[indices]),
                        torch.tensor(train["y"][indices],dtype=torch.float32),
                        torch.tensor(base[indices],dtype=torch.float32),
                        torch.tensor(weights,dtype=torch.float32)),
                        batch_size=protocol["batch_size"], shuffle=True)
    model = EnergyLSTM(x.shape[-1], config["hidden"])
    optimizer = torch.optim.AdamW(model.parameters(), lr=protocol["lr"], weight_decay=protocol["weight_decay"])
    best, best_epoch, best_state, stale, history = float("inf"), 0, None, 0, []
    started = time.perf_counter()
    for epoch in range(1, (fixed_epochs or protocol["epochs_max"])+1):
        model.train()
        for bx, by, anchor, weight in loader:
            optimizer.zero_grad()
            prediction = anchor*torch.exp(model(bx))
            # Smooth relative absolute error; aligned with percentage-error selection.
            relative = (prediction-by)/by
            loss = (torch.sqrt(relative.square()+0.01**2)*weight).mean()
            if not torch.isfinite(loss):
                raise ValueError("Nonfinite training loss")
            loss.backward(); torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0); optimizer.step()
        if fixed_epochs is not None:
            continue
        prediction = predict_network(model, scaler, config, val, reference)
        score = group_metrics(val, prediction)["flight_macro_mape_pct"]
        history.append({"epoch": epoch, "validation_macro_mape_pct": score})
        if score < best - 1e-4:
            best, best_epoch, best_state, stale = score, epoch, copy.deepcopy(model.state_dict()), 0
        else:
            stale += 1
        if stale >= protocol["patience"]:
            break
    if fixed_epochs is None:
        model.load_state_dict(best_state)
    else:
        best_epoch = fixed_epochs
    return model.eval(), reference, {"seed": seed, "best_epoch": best_epoch,
          "best_validation_macro_mape_pct": best if fixed_epochs is None else None,
          "elapsed_s": time.perf_counter()-started, "history": history}


def make_competitors(protocol):
    for alpha in protocol["baseline_search"]["ridge_alpha"]:
        yield f"ridge_residual_a{alpha}", make_pipeline(StandardScaler(), Ridge(alpha=alpha))
    for leaves in protocol["baseline_search"]["tree_leaves"]:
        for iterations in protocol["baseline_search"]["tree_iterations"]:
            yield f"tree_residual_l{leaves}_i{iterations}", HistGradientBoostingRegressor(
                max_iter=iterations, max_leaf_nodes=leaves, min_samples_leaf=25,
                l2_regularization=1, learning_rate=0.05, early_stopping=False, random_state=42)


def fit(out):
    p = check_protocol(out)
    if (out/"selection.json").exists() or (out/"TEST_OPENED.json").exists():
        raise ValueError("Already fitted/tested; do not overwrite experiments")
    frames, _, _ = read_dataset(p["source"])
    # Test and extra are not passed to any fitting, scaler, stopping or ranking routine.
    train = build_windows(frames, p["development_fit"])
    val = build_windows(frames, p["development_validation"])
    final_train = build_windows(frames, p["splits"]["train"])
    dev, final = out/"development", out/"models"
    dev.mkdir(exist_ok=True); final.mkdir(exist_ok=True)
    leaderboard = {}
    for config in p["configs"]:
        scaler = fit_scaler(frames, p["development_fit"], config["features"])
        seed_logs = []
        for seed in p["seeds"]:
            model, ref, log = train_network(train, val, scaler, config, seed, p)
            seed_logs.append(log)
            print(json.dumps({"stage": "development", "candidate": config["name"], "seed": seed,
                              "best_epoch": log["best_epoch"], "macro_mape": log["best_validation_macro_mape_pct"]}), flush=True)
        score = float(np.mean([r["best_validation_macro_mape_pct"] for r in seed_logs]))
        epochs = int(np.median([r["best_epoch"] for r in seed_logs]))
        leaderboard[config["name"]] = {"config": config, "selection_score": score,
                                        "final_epochs": epochs, "seeds": seed_logs}
        write_json(dev/"lstm_search.json", leaderboard)
    selected = min(leaderboard, key=lambda n: leaderboard[n]["selection_score"])
    baselines = causal_baselines(val)
    baseline_dev = {n: group_metrics(val, v) for n,v in baselines.items()}
    tx, vx = tabular_features(train), tabular_features(val)
    residual_target = np.log(train["y"]/train["base"])
    for name, competitor in make_competitors(p):
        competitor.fit(tx, residual_target)
        pred = val["base"]*np.exp(competitor.predict(vx))
        baseline_dev[name] = group_metrics(val, pred)
    comparator = min(baseline_dev, key=lambda n: baseline_dev[n]["flight_macro_mape_pct"])
    write_json(dev/"baselines.json", baseline_dev)
    selection = {"selected_lstm": selected, "selected_comparator": comparator,
                 "lstm_validation_score": leaderboard[selected]["selection_score"],
                 "comparator_validation_score": baseline_dev[comparator]["flight_macro_mape_pct"],
                 "selection_basis": p["selection"], "final_models": {}}
    # Every architecture is finalized before opening test. They remain ablations;
    # no later test winner is substituted for the preselected candidate.
    for name, entry in leaderboard.items():
        config = entry["config"]
        scaler = fit_scaler(frames, p["splits"]["train"], config["features"])
        joblib.dump(scaler, final/f"{name}_scaler.joblib")
        records = []
        for seed in p["seeds"]:
            model, ref, log = train_network(final_train, None, scaler, config, seed, p, entry["final_epochs"])
            path = final/f"{name}_seed{seed}.pt"
            torch.save({"state_dict": model.state_dict(), "config": config, "reference_ah": ref,
                        "features": FEATURE_SETS[config["features"]], "seed": seed,
                        "protocol_sha256": sha256(out/"protocol.json")}, path)
            records.append({"file": path.name, "sha256": sha256(path), "reference_ah": ref,
                            "seed": seed, "epochs": entry["final_epochs"]})
        selection["final_models"][name] = records
        print(json.dumps({"stage": "final_fit", "candidate": name, "epochs": entry["final_epochs"]}), flush=True)
    final_tx = tabular_features(final_train)
    for name, competitor in make_competitors(p):
        competitor.fit(final_tx, np.log(final_train["y"]/final_train["base"]))
        joblib.dump(competitor, final/f"{name}.joblib")
    selection["artifact_sha256"] = {f.name: sha256(f) for f in sorted(final.iterdir())}
    write_json(out/"selection.json", selection)
    print(json.dumps({"selected_lstm": selected, "selected_comparator": comparator,
                      "status": "all choices frozen; test not opened"}), flush=True)


def load_network(out, name, record):
    checkpoint = torch.load(out/"models"/record["file"], map_location="cpu", weights_only=False)
    config = checkpoint["config"]
    model = EnergyLSTM(len(FEATURE_SETS[config["features"]]), config["hidden"])
    model.load_state_dict(checkpoint["state_dict"])
    return model.eval(), joblib.load(out/"models"/f"{name}_scaler.joblib"), config, checkpoint["reference_ah"]


def evaluate(out):
    p = check_protocol(out)
    s = json.loads((out/"selection.json").read_text())
    if (out/"TEST_OPENED.json").exists():
        raise ValueError("Test already opened: results are immutable; do not tune against them")
    for filename, expected in s["artifact_sha256"].items():
        if sha256(out/"models"/filename) != expected:
            raise ValueError(f"Changed model artifact: {filename}")
    write_json(out/"TEST_OPENED.json", {"selection_sha256": sha256(out/"selection.json"),
                                        "opened_local": time.strftime("%Y-%m-%d %H:%M:%S%z")})
    torch.set_num_threads(1)
    frames, meta, _ = read_dataset(p["source"])
    report = {"selected_lstm": s["selected_lstm"], "selected_comparator": s["selected_comparator"],
              "prior_test_exposure": p["prior_test_exposure"], "groups": {}}
    all_rows, inference_times = [], []
    for group in ("test", "extra"):
        data = build_windows(frames, p["splits"][group])
        predictions = causal_baselines(data)
        tab = tabular_features(data)
        for name, _ in make_competitors(p):
            competitor = joblib.load(out/"models"/f"{name}.joblib")
            predictions[name] = data["base"]*np.exp(competitor.predict(tab))
        seeds = {}
        for name, records in s["final_models"].items():
            each = []
            for record in records:
                model, scaler, config, ref = load_network(out, name, record)
                prediction = predict_network(model, scaler, config, data, ref)
                each.append(prediction)
            predictions[name] = np.mean(each, axis=0)
            seeds[name] = [group_metrics(data, values) for values in each]
        details = {name: group_metrics(data, values) for name, values in predictions.items()}
        report["groups"][group] = {"flights": p["splits"][group], "methods": details, "lstm_seeds": seeds}
        for i in range(len(data["y"])):
            all_rows.append({"split": group, "flight_id": data["flight"][i],
                "prediction_available_at_s": float(data["time"][i]), "target_available_at_s": float(data["time"][i]+10),
                "truth_consumption_ah": float(data["y"][i]), "current_capacity_ah": float(data["capacity"][i]),
                **{name: float(values[i]) for name,values in predictions.items()}})
        # Measure the actual chosen three-member FP32 predictor at batch=1,
        # including feature selection/scaling; no fabricated service/network latency.
        if group == "test":
            selected = [load_network(out, s["selected_lstm"], r) for r in s["final_models"][s["selected_lstm"]]]
            for k in range(20 + 300):
                one = subset(data, slice(k % len(data["y"]), k % len(data["y"])+1))
                started = time.perf_counter()
                out_values = [predict_network(m,sc,c,one,ref,1) for m,sc,c,ref in selected]
                np.mean(out_values, axis=0)
                if k >= 20:
                    inference_times.append((time.perf_counter()-started)*1000)
    report["latency_local_cpu_fp32_three_seed_ensemble_ms"] = {
        "n": len(inference_times), "median": float(np.median(inference_times)),
        "p99": float(np.percentile(inference_times,99)), "max": float(max(inference_times)),
        "scope": "includes scaling and all three models; no HTTP/backend/browser or edge-device timing"}
    gate = {}
    for group, required_wins in (("test",2), ("extra",3)):
        methods = report["groups"][group]["methods"]
        model = methods[s["selected_lstm"]]
        comparator = methods[s["selected_comparator"]]
        history = methods["history_10s"]
        wins = sum(model["per_flight"][f]["mape_pct"] < comparator["per_flight"][f]["mape_pct"]
                   for f in model["per_flight"])
        gain = (1-model["flight_macro_mape_pct"]/comparator["flight_macro_mape_pct"])*100
        history_gain = (1-model["flight_macro_mape_pct"]/history["flight_macro_mape_pct"])*100
        seed_scores = [m["flight_macro_mape_pct"] for m in report["groups"][group]["lstm_seeds"][s["selected_lstm"]]]
        stable = all(v < comparator["flight_macro_mape_pct"] for v in seed_scores)
        gate[group] = {"relative_macro_improvement_over_comparator_pct": gain,
            "relative_macro_improvement_over_history_pct": history_gain,
            "flight_wins": wins, "required_wins": required_wins,
            "all_three_seeds_better": stable,
            "passes": bool(gain>=10 and history_gain>=10 and wins>=required_wins and stable and model["nonpositive_predictions"]==0)}
    report["gate"] = gate
    report["promotion_eligible"] = all(v["passes"] for v in gate.values())
    report["online_model_changed"] = False
    write_json(out/"evaluation.json", report)
    write_json(out/"heldout_predictions.json", all_rows)
    write_json(out/"candidate_manifest.json", {
        "version": p["experiment"], "architecture": s["selected_lstm"],
        "mode": "arithmetic mean of three independently trained FP32 models",
        "members": s["final_models"][s["selected_lstm"]],
        "scaler_sha256": s["artifact_sha256"][s["selected_lstm"]+"_scaler.joblib"],
        "target": p["target"], "availability": p["availability"],
        "protocol_sha256": sha256(out/"protocol.json"), "promotion_eligible": report["promotion_eligible"],
        "validated_on_real_data": False, "deployed": False,
        "prediction_transform": "history_10s * exp(learned_log_residual), no post-hoc correction"})
    print(json.dumps({"selected": s["selected_lstm"], "comparator": s["selected_comparator"],
                      "gate": gate, "latency": report["latency_local_cpu_fp32_three_seed_ensemble_ms"]}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=["prepare", "fit", "evaluate"])
    parser.add_argument("--source", type=Path, default=Path("/Users/kedong/Downloads/dataset_v2.zip"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.stage == "prepare":
        prepare(args.source, args.output)
    elif args.stage == "fit":
        fit(args.output)
    else:
        evaluate(args.output)


if __name__ == "__main__":
    main()
