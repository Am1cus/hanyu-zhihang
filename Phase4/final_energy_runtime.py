"""Standalone frozen residual-LSTM runtime (numpy + torch; no sklearn fitting).

Accepts exactly 30 completed one-second mean telemetry bins. It predicts a
ten-second charge difference, not capacity aging, SOH, range or flight time.
Inference validity and research/real-flight validation are separate statuses.
"""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import torch
from torch import nn

CONTRACT = "completed_1hz_bin_means_right_boundary_v1"
RAW_FIELDS = ["current", "wind_speed", "velocity_x", "velocity_y", "velocity_z",
              "wind_x", "wind_y", "wind_z", "remaining_capacity_ah", "available_at_s"]
FEATURES = ["current", "wind_speed", "horizontal_speed", "velocity_z",
            "relative_air_speed", "wind_along_velocity"]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ResidualLSTM(nn.Module):
    def __init__(self):
        super().__init__()
        self.lstm = nn.LSTM(6, 32, batch_first=True)
        self.head = nn.Sequential(nn.Linear(32,32),nn.Tanh(),nn.Linear(32,1))

    def forward(self, x):
        return self.head(self.lstm(x)[0][:,-1]).squeeze(-1)


class FrozenEnergyPredictor:
    def __init__(self, release_dir):
        self.root = Path(release_dir)
        lock = json.loads((self.root/"RELEASE_LOCK.json").read_text())
        if digest(self.root/"manifest.json") != lock["manifest_sha256"]:
            raise ValueError("Release manifest fingerprint mismatch")
        self.manifest = json.loads((self.root/"manifest.json").read_text())
        for filename, expected in self.manifest["artifact_sha256"].items():
            if Path(filename).name != filename or digest(self.root/filename) != expected:
                raise ValueError(f"Release artifact fingerprint mismatch: {filename}")
        if self.manifest["features"] != FEATURES:
            raise ValueError("Unsupported feature contract")
        scaler = json.loads((self.root/"scaler.json").read_text())
        self.mean = np.asarray(scaler["mean"],dtype=np.float64)
        self.scale = np.asarray(scaler["scale"],dtype=np.float64)
        if self.mean.shape != (6,) or self.scale.shape != (6,) or not (self.scale>0).all():
            raise ValueError("Invalid frozen scaler")
        self.models = []
        torch.set_num_threads(1)
        for member in self.manifest["members"]:
            checkpoint = torch.load(self.root/member["file"],map_location="cpu",weights_only=True)
            if checkpoint["features"] != FEATURES or not checkpoint["config"]["residual"]:
                raise ValueError("Checkpoint architecture/feature mismatch")
            model = ResidualLSTM()
            model.load_state_dict(checkpoint["state_dict"])
            self.models.append(model.eval())

    def predict(self, samples, *, sampling_contract, data_source):
        started = time.perf_counter()
        status = {"valid":False, "model_version":self.manifest["model_version"],
                  "method":"motion_residual_lstm_ensemble", "precision":"FP32",
                  "member_count":len(self.models), "forecast_horizon_seconds":10,
                  "research_status":"frozen_candidate_pending_independent_confirmation",
                  "validated_on_real_data":False, "project_acceptance_passed":False,
                  "predicted_consumption_ah":None, "predicted_future_capacity_ah":None}

        def invalid(reason):
            return {**status,"reason":reason,"inference_time_ms":(time.perf_counter()-started)*1000}

        if sampling_contract != CONTRACT:
            return invalid("unsupported_sampling_contract_no_automatic_conversion")
        if data_source != "AIRSIM_FORMULA_BATTERY":
            return invalid("unsupported_data_domain_requires_separate_validation")
        if len(samples) != 30:
            return invalid("requires_exactly_30_completed_bins")
        try:
            raw = np.array([[s[k] for k in RAW_FIELDS] for s in samples],dtype=np.float64)
        except (KeyError,TypeError,ValueError):
            return invalid("missing_or_invalid_sensor_field")
        if not np.isfinite(raw).all():
            return invalid("nonfinite_telemetry")
        if any(not isinstance(s.get("flight_id"), str) or not s["flight_id"] for s in samples):
            return invalid("requires_flight_identity_on_every_sample")
        for identity in ("flight_id","run_id"):
            if any(identity in s for s in samples):
                identities = [s.get(identity) for s in samples]
                if any(not isinstance(v,(str,int)) for v in identities) or len(set(identities))!=1:
                    return invalid("mixed_or_missing_"+identity)
        current, wind, vx, vy, vz, wx, wy, wz, charge, clock = raw.T
        if not np.allclose(np.diff(clock),1,rtol=0,atol=1e-9):
            return invalid("noncontiguous_source_clock")
        base = charge[-11]-charge[-1]
        if base<=0 or (charge<=0).any() or (np.diff(charge)>1e-9).any() or (current<0).any() or (wind<0).any():
            return invalid("invalid_discharge_window")
        horizontal = np.hypot(vx,vy)
        features = np.column_stack((current,wind,horizontal,vz,
                       np.sqrt((vx-wx)**2+(vy-wy)**2+(vz-wz)**2),
                       (wx*vx+wy*vy)/np.maximum(horizontal,0.1))).astype(np.float32)
        bounds = self.manifest["training_feature_ranges"]
        outside = [name for i,name in enumerate(FEATURES)
                   if (features[:,i]<bounds[name]["min"]).any() or (features[:,i]>bounds[name]["max"]).any()]
        # Same float32 in-place arithmetic as fitted StandardScaler.transform.
        features -= self.mean
        features /= self.scale
        x = torch.from_numpy(features[None,:,:])
        with torch.inference_mode():
            members = np.array([base*np.exp(float(m(x)[0])) for m in self.models])
        prediction = float(members.mean())
        if not np.isfinite(members).all() or (members<=0).any() or prediction>charge[-1]:
            return invalid("physically_invalid_prediction_no_clamping")
        return {**status, "valid":True,"reason":"candidate_inference_only_not_acceptance_certification",
                "prediction_available_at_s":float(clock[-1]),"target_available_at_s":float(clock[-1]+10),
                "history_10s_baseline_ah":float(base),"predicted_consumption_ah":prediction,
                "predicted_future_capacity_ah":float(charge[-1]-prediction),
                "member_consumption_ah":members.tolist(),
                "outside_training_range_features":outside,
                "inference_time_ms":(time.perf_counter()-started)*1000}


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release",type=Path,default=Path(__file__).parent)
    parser.add_argument("--request",type=Path,required=True,
                        help="JSON: samples, sampling_contract, data_source (no future labels needed)")
    args=parser.parse_args()
    request=json.loads(args.request.read_text())
    result=FrozenEnergyPredictor(args.release).predict(request["samples"],
            sampling_contract=request["sampling_contract"],data_source=request["data_source"])
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))


if __name__=="__main__":
    main()
