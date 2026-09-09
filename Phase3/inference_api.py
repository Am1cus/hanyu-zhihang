import json
import hashlib
import os
import time
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

import joblib
import numpy as np
import pandas as pd
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from torch import nn
from Phase4.energy_v3_service import EnergyV3Service, unavailable as energy_unavailable

from Phase4.flight_time_model import (
    FEATURE_COLUMNS as FLIGHT_TIME_FEATURE_COLUMNS,
    LOOKBACK as FLIGHT_TIME_LOOKBACK,
    FlightTimeLSTM,
)
from Phase4.airsim_capacity_model import (
    FEATURE_COLUMNS as AIRSIM_CAPACITY_FEATURE_COLUMNS,
    FORECAST_HORIZON_SECONDS as AIRSIM_CAPACITY_HORIZON,
    LOOKBACK as AIRSIM_CAPACITY_LOOKBACK,
    AirSimCapacityLSTM,
)


LOOKBACK = 10
FEATURE_COLUMNS = [
    "temperature_C",
    "wind_speed_ms",
    "voltage_V",
    "current_A",
    "soc_pct",
]
STANDARDIZED_FEATURE_COLUMNS = [
    "temperature_C",
    "wind_speed_ms",
    "voltage_V",
    "current_A",
]
MODEL_VERSION = "multi_lstm_quantized_v1"
FLIGHT_TIME_MODEL_VERSION = "flight_time_lstm_v2"
AIRSIM_CAPACITY_MODEL_VERSION = "airsim_capacity_lstm_v2"

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(CURRENT_DIR)
PHASE1_DIR = os.path.join(PROJECT_DIR, "Phase1")
PHASE2_DIR = os.path.join(PROJECT_DIR, "Phase2")
PHASE4_DIR = os.path.join(PROJECT_DIR, "Phase4")
MODEL_PATH = os.path.join(PHASE2_DIR, "multi_lstm_model_quantized.pth")
SCALER_PATH = os.path.join(PHASE1_DIR, "scaler.pkl")
FLIGHT_TIME_MODEL_PATH = os.path.join(PHASE4_DIR, "models", "flight_time_lstm_v2_quantized.pth")
FLIGHT_TIME_SCALER_PATH = os.path.join(PHASE4_DIR, "models", "flight_time_scaler_v2.pkl")
AIRSIM_CAPACITY_MODEL_PATH = os.path.join(PHASE4_DIR, "models", "airsim_capacity_lstm_v2_quantized.pth")
AIRSIM_CAPACITY_SCALER_PATH = os.path.join(PHASE4_DIR, "models", "airsim_capacity_scaler_v2.pkl")
AIRSIM_CAPACITY_REPORT_PATH = os.path.join(PHASE4_DIR, "models", "airsim_capacity_validation_v2.json")
TRAINING_DATASET_PATH = os.path.join(PHASE1_DIR, "training_dataset_v1.csv")
CAPACITY_VALIDATION_BATTERIES = ["B5", "B6", "B7", "B18"]
CAPACITY_VALIDATION_CASES_PER_BATTERY = 5

MODEL = None
SCALER = None
FLIGHT_TIME_MODEL = None
FLIGHT_TIME_SCALER = None
AIRSIM_CAPACITY_MODEL = None
AIRSIM_CAPACITY_SCALER = None
AIRSIM_CAPACITY_REPORT = None
AIRSIM_CAPACITY_MODEL_SHA256 = None
AIRSIM_CAPACITY_SCALER_SHA256 = None
CAPACITY_VALIDATION_CASES = []
ENERGY_V3 = None
ENERGY_V3_LOAD_ERROR = None


class EnergyV3Request(BaseModel):
    drone_id: int
    sampling_contract: str
    data_source: str
    samples: List[dict] = Field(max_length=30)


class MultiFeatureLSTM(nn.Module):
    def __init__(self, input_size, hidden_size=64, num_layers=2, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout,
        )
        self.output_layer = nn.Linear(hidden_size, 1)

    def forward(self, inputs):
        lstm_output, _ = self.lstm(inputs)
        last_time_step = lstm_output[:, -1, :]
        return self.output_layer(last_time_step)


class CycleFeatures(BaseModel):
    temperature_C: float = Field(ge=-60, le=60)
    wind_speed_ms: float = Field(ge=0, le=100)
    voltage_V: float = Field(gt=0, le=100)
    current_A: float = Field(ge=-1000, le=1000)
    soc_pct: float = Field(ge=0, le=100)


class PredictionRequest(BaseModel):
    cycles: List[CycleFeatures] = Field(min_length=LOOKBACK, max_length=LOOKBACK)


class PredictionResponse(BaseModel):
    predicted_capacity_Ah: float
    input_cycles: int
    inference_time_ms: float
    model_version: str


class CapacityValidationResponse(PredictionResponse):
    valid: bool = True
    case_index: int
    total_cases: int
    battery_id: str
    input_cycle_start: int
    input_cycle_end: int
    target_cycle: int
    input_soc_pct: List[float]
    true_capacity_Ah: float
    absolute_error_Ah: float
    absolute_percentage_error_pct: float


class FlightTelemetrySample(BaseModel):
    timestamp_s: float = Field(ge=0)
    env_temperature_C: float = Field(ge=-60, le=60)
    wind_speed_ms: float = Field(ge=0, le=100)
    voltage_V: float = Field(gt=0, le=100)
    current_A: float = Field(ge=-1000, le=1000)
    battery_level_pct: float = Field(ge=0, le=100)
    speed_ms: float = Field(ge=0, le=200)
    altitude_m: float = Field(ge=-1000, le=20000)
    remaining_capacity_Ah: Optional[float] = Field(default=None, gt=0, le=1000)


class FlightTimeRequest(BaseModel):
    drone_id: int
    samples: List[FlightTelemetrySample] = Field(
        min_length=FLIGHT_TIME_LOOKBACK,
        max_length=FLIGHT_TIME_LOOKBACK,
    )


class FlightTimeResponse(BaseModel):
    valid: bool
    remaining_flight_time_s: Optional[float] = None
    inference_time_ms: Optional[float] = None
    model_version: str
    reason: Optional[str] = None
    validated_on_real_data: bool = False


class AirSimCapacityResponse(BaseModel):
    valid: bool
    predicted_capacity_Ah: Optional[float] = None
    predicted_consumption_Ah: Optional[float] = None
    current_measured_capacity_Ah: Optional[float] = None
    forecast_horizon_s: int = AIRSIM_CAPACITY_HORIZON
    inference_time_ms: Optional[float] = None
    model_version: str = AIRSIM_CAPACITY_MODEL_VERSION
    model_sha256: Optional[str] = None
    scaler_sha256: Optional[str] = None
    test_mape_pct: Optional[float] = None
    reason: Optional[str] = None
    data_source: str = "AirSim simulation"
    validated_on_real_data: bool = False
    output_transform: str = "current_measured_capacity - raw_lstm_consumption; no_linear_calibration"


def select_quantization_engine():
    supported_engines = torch.backends.quantized.supported_engines
    for engine_name in ["qnnpack", "x86", "fbgemm"]:
        if engine_name in supported_engines:
            torch.backends.quantized.engine = engine_name
            return engine_name
    raise RuntimeError("当前 PyTorch 环境没有可用的动态量化后端")


def load_quantized_model():
    if not os.path.exists(MODEL_PATH):
        raise FileNotFoundError(f"未找到量化模型：{MODEL_PATH}")

    select_quantization_engine()
    float_model = MultiFeatureLSTM(input_size=len(FEATURE_COLUMNS))
    quantized_model = torch.quantization.quantize_dynamic(
        float_model,
        {nn.LSTM},
        dtype=torch.qint8,
    )

    state_dict = torch.load(MODEL_PATH, map_location="cpu", weights_only=False)
    quantized_model.load_state_dict(state_dict)
    quantized_model.eval()
    return quantized_model


def load_scaler():
    if not os.path.exists(SCALER_PATH):
        raise FileNotFoundError(f"未找到标准化器：{SCALER_PATH}")
    return joblib.load(SCALER_PATH)


def load_optional_flight_time_assets():
    if not os.path.exists(FLIGHT_TIME_MODEL_PATH) or not os.path.exists(FLIGHT_TIME_SCALER_PATH):
        return None, None
    select_quantization_engine()
    float_model = FlightTimeLSTM()
    quantized_model = torch.quantization.quantize_dynamic(
        float_model,
        {nn.LSTM},
        dtype=torch.qint8,
    )
    state_dict = torch.load(FLIGHT_TIME_MODEL_PATH, map_location="cpu", weights_only=False)
    quantized_model.load_state_dict(state_dict)
    quantized_model.eval()
    return quantized_model, joblib.load(FLIGHT_TIME_SCALER_PATH)


def load_airsim_capacity_assets():
    global AIRSIM_CAPACITY_MODEL_SHA256, AIRSIM_CAPACITY_SCALER_SHA256
    if not os.path.exists(AIRSIM_CAPACITY_MODEL_PATH) or not os.path.exists(AIRSIM_CAPACITY_SCALER_PATH):
        raise FileNotFoundError("未找到AirSim容量模型或标准化器")
    select_quantization_engine()
    float_model = AirSimCapacityLSTM()
    quantized_model = torch.quantization.quantize_dynamic(
        float_model,
        {nn.LSTM},
        dtype=torch.qint8,
    )
    state_dict = torch.load(AIRSIM_CAPACITY_MODEL_PATH, map_location="cpu", weights_only=False)
    quantized_model.load_state_dict(state_dict)
    quantized_model.eval()
    with open(AIRSIM_CAPACITY_MODEL_PATH, "rb") as model_file:
        AIRSIM_CAPACITY_MODEL_SHA256 = hashlib.sha256(model_file.read()).hexdigest()
    with open(AIRSIM_CAPACITY_SCALER_PATH, "rb") as scaler_file:
        AIRSIM_CAPACITY_SCALER_SHA256 = hashlib.sha256(scaler_file.read()).hexdigest()
    report = None
    if os.path.exists(AIRSIM_CAPACITY_REPORT_PATH):
        with open(AIRSIM_CAPACITY_REPORT_PATH, encoding="utf-8") as report_file:
            report = json.load(report_file)
    return quantized_model, joblib.load(AIRSIM_CAPACITY_SCALER_PATH), report


def prepare_input(cycles, scaler):
    raw_values = pd.DataFrame(
        [
            [
                cycle.temperature_C,
                cycle.wind_speed_ms,
                cycle.voltage_V,
                cycle.current_A,
            ]
            for cycle in cycles
        ],
        columns=STANDARDIZED_FEATURE_COLUMNS,
        dtype=np.float64,
    )
    standardized_values = scaler.transform(raw_values)
    soc_values = np.array([[cycle.soc_pct] for cycle in cycles], dtype=np.float64)
    feature_values = np.concatenate([standardized_values, soc_values], axis=1)
    return torch.tensor(feature_values, dtype=torch.float32).unsqueeze(0)


def build_capacity_validation_cases(scaler):
    """构造训练区间之外的20组可复现演示样本。"""
    frame = pd.read_csv(TRAINING_DATASET_PATH, encoding="utf-8-sig")
    cases = []
    for battery_id in CAPACITY_VALIDATION_BATTERIES:
        battery = (
            frame[frame["battery_id"] == battery_id]
            .sort_values("cycle")
            .reset_index(drop=True)
        )
        split_index = int(len(battery) * 0.8)
        for target_index in range(
            split_index,
            split_index + CAPACITY_VALIDATION_CASES_PER_BATTERY,
        ):
            feature_window = battery.iloc[target_index - LOOKBACK : target_index]
            raw_values = scaler.inverse_transform(
                feature_window[STANDARDIZED_FEATURE_COLUMNS]
            )
            cycles = [
                CycleFeatures(
                    temperature_C=float(raw_values[row_index, 0]),
                    wind_speed_ms=float(raw_values[row_index, 1]),
                    voltage_V=float(raw_values[row_index, 2]),
                    current_A=float(raw_values[row_index, 3]),
                    soc_pct=float(row["soc_pct"]),
                )
                for row_index, (_, row) in enumerate(feature_window.iterrows())
            ]
            target = battery.iloc[target_index]
            cases.append(
                {
                    "battery_id": battery_id,
                    "input_cycle_start": int(feature_window.iloc[0]["cycle"]),
                    "input_cycle_end": int(feature_window.iloc[-1]["cycle"]),
                    "target_cycle": int(target["cycle"]),
                    "true_capacity_Ah": float(target["capacity_Ah"]),
                    "cycles": cycles,
                }
            )
    return cases


def run_capacity_prediction(cycles):
    if MODEL is None or SCALER is None:
        raise HTTPException(status_code=503, detail="模型尚未加载完成")

    input_tensor = prepare_input(cycles, SCALER)
    start_time = time.perf_counter()
    with torch.no_grad():
        prediction = MODEL(input_tensor).item()
    inference_time_ms = (time.perf_counter() - start_time) * 1000
    return PredictionResponse(
        predicted_capacity_Ah=round(prediction, 6),
        input_cycles=len(cycles),
        inference_time_ms=round(inference_time_ms, 4),
        model_version=MODEL_VERSION,
    )


@asynccontextmanager
async def lifespan(application):
    global MODEL, SCALER, FLIGHT_TIME_MODEL, FLIGHT_TIME_SCALER
    global AIRSIM_CAPACITY_MODEL, AIRSIM_CAPACITY_SCALER, AIRSIM_CAPACITY_REPORT
    global CAPACITY_VALIDATION_CASES
    global ENERGY_V3, ENERGY_V3_LOAD_ERROR
    torch.set_num_threads(1)
    MODEL = load_quantized_model()
    SCALER = load_scaler()
    CAPACITY_VALIDATION_CASES = build_capacity_validation_cases(SCALER)
    FLIGHT_TIME_MODEL, FLIGHT_TIME_SCALER = load_optional_flight_time_assets()
    AIRSIM_CAPACITY_MODEL, AIRSIM_CAPACITY_SCALER, AIRSIM_CAPACITY_REPORT = load_airsim_capacity_assets()
    try:
        ENERGY_V3 = EnergyV3Service()
        ENERGY_V3_LOAD_ERROR = None
    except Exception:
        ENERGY_V3 = None
        ENERGY_V3_LOAD_ERROR = "candidate_artifacts_unavailable_or_integrity_failed"
        logging.exception("V3 candidate unavailable; legacy models remain available")
    yield
    MODEL = None
    SCALER = None
    FLIGHT_TIME_MODEL = None
    FLIGHT_TIME_SCALER = None
    AIRSIM_CAPACITY_MODEL = None
    AIRSIM_CAPACITY_SCALER = None
    AIRSIM_CAPACITY_REPORT = None
    CAPACITY_VALIDATION_CASES = []
    ENERGY_V3 = None


app = FastAPI(
    title="寒域智航容量预测 API",
    version="1.0.0",
    description="使用过去 10 个循环的多特征数据预测下一循环电池容量。",
    lifespan=lifespan,
)


@app.get("/health")
def health_check():
    airsim_metrics = (AIRSIM_CAPACITY_REPORT or {}).get("quantized_test_metrics", {})
    return {
        "status": "ok",
        "model_loaded": MODEL is not None,
        "model_version": MODEL_VERSION,
        "flight_time_model_available": FLIGHT_TIME_MODEL is not None,
        "flight_time_model_version": FLIGHT_TIME_MODEL_VERSION,
        "airsim_capacity_model_available": AIRSIM_CAPACITY_MODEL is not None,
        "airsim_capacity_model_version": AIRSIM_CAPACITY_MODEL_VERSION,
        "airsim_capacity_test_mape_pct": airsim_metrics.get("mape_pct"),
        "airsim_capacity_forecast_horizon_s": AIRSIM_CAPACITY_HORIZON,
        "quantization_engine": torch.backends.quantized.engine,
        "energy_v3_available": ENERGY_V3 is not None,
        "energy_v3_status": "frozen_candidate_pending_independent_confirmation",
        "energy_v3_load_error": ENERGY_V3_LOAD_ERROR,
    }


@app.post("/api/predict/energy-v3")
def predict_energy_v3(request: EnergyV3Request):
    if ENERGY_V3 is None:
        return energy_unavailable(ENERGY_V3_LOAD_ERROR or "candidate_not_loaded")
    return ENERGY_V3.predict(request.model_dump())


@app.get("/api/models/energy-v3/report")
def energy_v3_report():
    if ENERGY_V3 is None:
        raise HTTPException(status_code=503, detail="V3候选未加载")
    return ENERGY_V3.report()


@app.get("/api/models/airsim-capacity/report")
def airsim_capacity_report():
    if AIRSIM_CAPACITY_REPORT is None:
        raise HTTPException(status_code=503, detail="AirSim模型验证报告未加载")
    result = dict(AIRSIM_CAPACITY_REPORT)
    result["model_sha256"] = AIRSIM_CAPACITY_MODEL_SHA256
    result["scaler_sha256"] = AIRSIM_CAPACITY_SCALER_SHA256
    baseline_path = os.path.join(PHASE4_DIR, "reports", "capacity_baselines_v2.json")
    if os.path.exists(baseline_path):
        with open(baseline_path, encoding="utf-8") as baseline_file:
            result["baseline_comparison"] = json.load(baseline_file)
    return result


@app.post("/predict", response_model=PredictionResponse)
def predict_capacity(request: PredictionRequest):
    return run_capacity_prediction(request.cycles)


@app.get(
    "/api/demo/capacity-validation/{case_index}",
    response_model=CapacityValidationResponse,
)
def predict_capacity_validation_case(case_index: int):
    if not CAPACITY_VALIDATION_CASES:
        raise HTTPException(status_code=503, detail="容量验证样本尚未加载完成")
    if case_index < 0 or case_index >= len(CAPACITY_VALIDATION_CASES):
        raise HTTPException(status_code=404, detail="容量验证样本编号不存在")

    case = CAPACITY_VALIDATION_CASES[case_index]
    prediction = run_capacity_prediction(case["cycles"])
    true_capacity = case["true_capacity_Ah"]
    absolute_error = abs(prediction.predicted_capacity_Ah - true_capacity)
    return CapacityValidationResponse(
        **prediction.model_dump(),
        case_index=case_index + 1,
        total_cases=len(CAPACITY_VALIDATION_CASES),
        battery_id=case["battery_id"],
        input_cycle_start=case["input_cycle_start"],
        input_cycle_end=case["input_cycle_end"],
        target_cycle=case["target_cycle"],
        input_soc_pct=[round(cycle.soc_pct, 3) for cycle in case["cycles"]],
        true_capacity_Ah=round(true_capacity, 6),
        absolute_error_Ah=round(absolute_error, 6),
        absolute_percentage_error_pct=round(absolute_error / true_capacity * 100, 4),
    )


@app.post("/api/predict/flight-time", response_model=FlightTimeResponse)
def predict_flight_time(request: FlightTimeRequest):
    if FLIGHT_TIME_MODEL is None or FLIGHT_TIME_SCALER is None:
        return FlightTimeResponse(
            valid=False,
            model_version=FLIGHT_TIME_MODEL_VERSION,
            reason="flight_time_model_not_available: AirSim数据尚未通过V2训练门禁",
        )

    frame = pd.DataFrame(
        [sample.model_dump() for sample in request.samples],
        columns=["timestamp_s", *FLIGHT_TIME_FEATURE_COLUMNS],
    )
    feature_values = FLIGHT_TIME_SCALER.transform(frame[FLIGHT_TIME_FEATURE_COLUMNS])
    input_tensor = torch.tensor(feature_values, dtype=torch.float32).unsqueeze(0)
    start_time = time.perf_counter()
    with torch.no_grad():
        prediction = max(0.0, FLIGHT_TIME_MODEL(input_tensor).item())
    inference_time_ms = (time.perf_counter() - start_time) * 1000
    return FlightTimeResponse(
        valid=True,
        remaining_flight_time_s=round(prediction, 3),
        inference_time_ms=round(inference_time_ms, 4),
        model_version=FLIGHT_TIME_MODEL_VERSION,
        validated_on_real_data=False,
    )


@app.post("/api/predict/airsim-capacity", response_model=AirSimCapacityResponse)
def predict_airsim_capacity(request: FlightTimeRequest):
    if AIRSIM_CAPACITY_MODEL is None or AIRSIM_CAPACITY_SCALER is None:
        return AirSimCapacityResponse(
            valid=False,
            reason="airsim_capacity_model_not_available",
        )
    if len(request.samples) != AIRSIM_CAPACITY_LOOKBACK:
        return AirSimCapacityResponse(
            valid=False,
            reason=f"需要最近{AIRSIM_CAPACITY_LOOKBACK}条1Hz遥测",
        )
    timestamps = np.asarray([sample.timestamp_s for sample in request.samples], dtype=float)
    if not np.isfinite(timestamps).all() or not np.allclose(np.diff(timestamps), 1.0, rtol=0, atol=1e-6):
        return AirSimCapacityResponse(valid=False, reason="non_contiguous_window: 需要连续30条1Hz数据")
    feature_array = np.asarray([[getattr(sample, name) for name in AIRSIM_CAPACITY_FEATURE_COLUMNS] for sample in request.samples], dtype=float)
    if not np.isfinite(feature_array).all():
        return AirSimCapacityResponse(valid=False, reason="non_finite_features")
    current_capacity = request.samples[-1].remaining_capacity_Ah
    if current_capacity is None or not np.isfinite(current_capacity):
        return AirSimCapacityResponse(
            valid=False,
            reason="缺少当前AirSim实测剩余容量",
        )

    frame = pd.DataFrame(
        [sample.model_dump() for sample in request.samples],
        columns=["timestamp_s", *AIRSIM_CAPACITY_FEATURE_COLUMNS],
    )
    feature_values = AIRSIM_CAPACITY_SCALER.transform(frame[AIRSIM_CAPACITY_FEATURE_COLUMNS])
    input_tensor = torch.tensor(feature_values, dtype=torch.float32).unsqueeze(0)
    start_time = time.perf_counter()
    with torch.no_grad():
        predicted_consumption = AIRSIM_CAPACITY_MODEL(input_tensor).item()
    inference_time_ms = (time.perf_counter() - start_time) * 1000
    predicted_capacity = current_capacity - predicted_consumption
    if not np.isfinite(predicted_consumption) or predicted_consumption < 0 or predicted_capacity < 0:
        return AirSimCapacityResponse(
            valid=False, reason="non_physical_model_output: 原始输出超出有效容量范围，未做截断修正",
            model_sha256=AIRSIM_CAPACITY_MODEL_SHA256, scaler_sha256=AIRSIM_CAPACITY_SCALER_SHA256,
        )
    metrics = (AIRSIM_CAPACITY_REPORT or {}).get("quantized_test_metrics", {})
    return AirSimCapacityResponse(
        valid=True,
        predicted_capacity_Ah=round(predicted_capacity, 6),
        predicted_consumption_Ah=round(predicted_consumption, 6),
        model_sha256=AIRSIM_CAPACITY_MODEL_SHA256,
        scaler_sha256=AIRSIM_CAPACITY_SCALER_SHA256,
        current_measured_capacity_Ah=round(current_capacity, 6),
        inference_time_ms=round(inference_time_ms, 4),
        test_mape_pct=metrics.get("mape_pct"),
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("inference_api:app", host="127.0.0.1", port=8000, reload=False)
