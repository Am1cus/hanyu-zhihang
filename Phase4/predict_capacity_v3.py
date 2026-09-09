"""Read-only CLI for the separately versioned V3 research candidate.

This does not replace the running FastAPI V2 service. It consumes completed 1Hz
bins from the same adapter as training, and never reads future labels to infer.
"""
import argparse
import json
import time
from pathlib import Path

import numpy as np
import torch

from capacity_v3 import ALL_FEATURES, LOOKBACK, predict_network, read_dataset, sha256
from train_capacity_v3 import load_network


class CapacityV3Predictor:
    def __init__(self, experiment, candidate=None):
        self.root = Path(experiment)
        self.selection = json.loads((self.root/"selection.json").read_text())
        self.manifest = json.loads((self.root/"candidate_manifest.json").read_text())
        self.name = candidate or self.selection["selected_lstm"]
        if self.name not in self.selection["final_models"]:
            raise ValueError("Unknown frozen candidate")
        self.is_primary = self.name == self.selection["selected_lstm"]
        filenames = [r["file"] for r in self.selection["final_models"][self.name]]
        filenames.append(self.name+"_scaler.joblib")
        for filename in filenames:
            if sha256(self.root/"models"/filename) != self.selection["artifact_sha256"][filename]:
                raise ValueError(f"Artifact fingerprint mismatch: {filename}")
        torch.set_num_threads(1)
        self.members = [load_network(self.root, self.name, r)
                        for r in self.selection["final_models"][self.name]]

    def predict_window(self, frame):
        started = time.perf_counter()
        status = {"valid": False, "model_version": self.manifest["version"]+"/"+self.name,
                  "architecture": self.name, "member_count": len(self.members),
                  "simulation_only": True, "promotion_eligible": bool(self.is_primary and self.manifest["promotion_eligible"]),
                  "selection_role": "preselected_primary" if self.is_primary else "exploratory_requires_fresh_confirmation",
                  "forecast_horizon_seconds": 10, "deployed": False,
                  "predicted_consumption_ah": None, "predicted_future_capacity_ah": None}
        if len(frame) != LOOKBACK:
            return {**status, "reason": "requires_exactly_30_completed_1hz_bins"}
        if not np.isfinite(frame[ALL_FEATURES+["remaining_capacity_ah","available_at_s"]].to_numpy()).all():
            return {**status, "reason": "nonfinite_or_missing_telemetry"}
        if not np.allclose(np.diff(frame.available_at_s),1,rtol=0,atol=1e-9):
            return {**status, "reason": "noncontiguous_source_clock"}
        charge = frame.remaining_capacity_ah.to_numpy()
        base = charge[-11]-charge[-1]
        if base<=0 or charge[-1]<=0 or (np.diff(charge)>1e-9).any():
            return {**status, "reason": "invalid_discharge_window"}
        data = {"x": frame[ALL_FEATURES].to_numpy(dtype=np.float32)[None,:,:],
                "base": np.array([base])}
        values = [float(predict_network(m,s,c,data,r,1)[0]) for m,s,c,r in self.members]
        consumption = float(np.mean(values))
        if not np.isfinite(consumption) or consumption<=0 or consumption>charge[-1]:
            return {**status, "reason": "physically_invalid_prediction_no_clamping"}
        return {**status, "valid": True, "reason": "research_candidate_not_real_flight_certification",
                "prediction_available_at_s": float(frame.available_at_s.iloc[-1]),
                "target_available_at_s": float(frame.available_at_s.iloc[-1]+10),
                "predicted_consumption_ah": consumption,
                "predicted_future_capacity_ah": float(charge[-1]-consumption),
                "history_10s_baseline_ah": float(base), "member_consumption_ah": values,
                "inference_time_ms": (time.perf_counter()-started)*1000}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, default=Path(__file__).parent/"experiments/capacity_v3_20260908")
    parser.add_argument("--source", type=Path, default=Path("/Users/kedong/Downloads/dataset_v2.zip"))
    parser.add_argument("--flight", required=True)
    parser.add_argument("--candidate", help="Optional frozen ablation; overrides are explicitly exploratory, never promoted")
    parser.add_argument("--available-at", type=float, default=60)
    args = parser.parse_args()
    frames, _, _ = read_dataset(args.source)
    if args.flight not in frames:
        parser.error("Unknown or quarantined flight")
    observed = frames[args.flight]
    window = observed[observed.available_at_s <= args.available_at].tail(LOOKBACK)
    if not len(window) or window.available_at_s.iloc[-1] != args.available_at:
        parser.error("Requested completed source-clock second is unavailable")
    result = CapacityV3Predictor(args.experiment, args.candidate).predict_window(window)
    print(json.dumps({"flight_id": args.flight, **result}, ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
