"""HTTP adapter around the immutable RC1 runtime; never retrain or rewrite it."""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

RELEASE = Path(__file__).parent / "releases/energy_residual_lstm_v3_rc1"
MODEL = "energy_residual_lstm_v3_rc1"
CONTRACT = "completed_1hz_bin_means_right_boundary_v1"
DOMAIN = "AIRSIM_FORMULA_BATTERY"


def unavailable(reason):
    return dict(valid=False, reason=reason, model_version=MODEL,
                predicted_capacity_Ah=None, predicted_consumption_Ah=None,
                forecast_horizon_s=10, research_status="frozen_candidate_pending_independent_confirmation",
                execution_mode="research_shadow", validated_on_real_data=False,
                project_acceptance_passed=False, data_source=DOMAIN)


class EnergyV3Service:
    def __init__(self, release=RELEASE):
        self.release = Path(release)
        lock = json.loads((self.release / "RELEASE_LOCK.json").read_text())
        manifest_bytes = (self.release / "manifest.json").read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != lock["manifest_sha256"]:
            raise ValueError("Release manifest fingerprint mismatch")
        self.manifest = json.loads(manifest_bytes)
        runtime = self.release / "runtime.py"
        if hashlib.sha256(runtime.read_bytes()).hexdigest() != self.manifest["artifact_sha256"]["runtime.py"]:
            raise ValueError("Release runtime fingerprint mismatch")
        spec = importlib.util.spec_from_file_location("frozen_energy_rc1", runtime)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.predictor = module.FrozenEnergyPredictor(self.release)
        self.manifest_sha256 = lock["manifest_sha256"]

    def predict(self, request):
        result = self.predictor.predict(request["samples"],
            sampling_contract=request.get("sampling_contract"), data_source=request.get("data_source"))
        # Alias units for the existing archive; keep every original runtime field.
        result.update(predicted_capacity_Ah=result.get("predicted_future_capacity_ah"),
                      predicted_consumption_Ah=result.get("predicted_consumption_ah"),
                      forecast_horizon_s=10, execution_mode="research_shadow", data_source=DOMAIN,
                      model_sha256=self.manifest_sha256,
                      model_hash_definition="sha256(frozen_release_manifest)",
                      scaler_sha256=self.manifest["artifact_sha256"]["scaler.json"],
                      sampling_contract=request.get("sampling_contract"))
        if result["valid"]:
            samples = request["samples"]
            current = np.asarray([s["current"] for s in samples], dtype=np.float32)
            result["baselines"] = {
                "history_10s": result["history_10s_baseline_ah"],
                "mean_current_20s": float(current[-20:].mean() * np.float32(10) / np.float32(3600)),
            }
        return result

    def report(self):
        decision = json.loads((self.release / "runtime_verification.json").read_text())
        return {"manifest": self.manifest, "manifest_sha256": self.manifest_sha256,
                "offline_recheck": decision, "execution_mode": "research_shadow",
                "independent_confirmation_passed": False, "validated_on_real_data": False}
