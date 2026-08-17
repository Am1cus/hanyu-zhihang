import os
import time
from contextlib import asynccontextmanager
from typing import List, Optional

import joblib
import numpy as np
import pandas as pd
import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from torch import nn

from Phase4.flight_time_model import (
    FEATURE_COLUMNS as FLIGHT_TIME_FEATURE_COLUMNS,
    LOOKBACK as FLIGHT_TIME_LOOKBACK,
    FlightTimeLSTM,
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

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(CURRENT_DIR)
PHASE1_DIR = os.path.join(PROJECT_DIR, "Phase1")
PHASE2_DIR = os.path.join(PROJECT_DIR, "Phase2")
PHASE4_DIR = os.path.join(PROJECT_DIR, "Phase4")
MODEL_PATH = os.path.join(PHASE2_DIR, "multi_lstm_model_quantized.pth")
SCALER_PATH = os.path.join(PHASE1_DIR, "scaler.pkl")
FLIGHT_TIME_MODEL_PATH = os.path.join(PHASE4_DIR, "models", "flight_time_lstm_v2_quantized.pth")
FLIGHT_TIME_SCALER_PATH = os.path.join(PHASE4_DIR, "models", "flight_time_scaler_v2.pkl")

MODEL = None
SCALER = None
FLIGHT_TIME_MODEL = None
FLIGHT_TIME_SCALER = None


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


class FlightTelemetrySample(BaseModel):
    timestamp_s: float = Field(ge=0)
    env_temperature_C: float = Field(ge=-60, le=60)
    wind_speed_ms: float = Field(ge=0, le=100)
    voltage_V: float = Field(gt=0, le=100)
    current_A: float = Field(ge=-1000, le=1000)
    battery_level_pct: float = Field(ge=0, le=100)
    speed_ms: float = Field(ge=0, le=200)
    altitude_m: float = Field(ge=-1000, le=20000)


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


@asynccontextmanager
async def lifespan(application):
    global MODEL, SCALER, FLIGHT_TIME_MODEL, FLIGHT_TIME_SCALER
    torch.set_num_threads(1)
    MODEL = load_quantized_model()
    SCALER = load_scaler()
    FLIGHT_TIME_MODEL, FLIGHT_TIME_SCALER = load_optional_flight_time_assets()
    yield
    MODEL = None
    SCALER = None
    FLIGHT_TIME_MODEL = None
    FLIGHT_TIME_SCALER = None


app = FastAPI(
    title="寒域智航容量预测 API",
    version="1.0.0",
    description="使用过去 10 个循环的多特征数据预测下一循环电池容量。",
    lifespan=lifespan,
)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "model_loaded": MODEL is not None,
        "model_version": MODEL_VERSION,
        "flight_time_model_available": FLIGHT_TIME_MODEL is not None,
        "flight_time_model_version": FLIGHT_TIME_MODEL_VERSION,
        "quantization_engine": torch.backends.quantized.engine,
    }


@app.post("/predict", response_model=PredictionResponse)
def predict_capacity(request: PredictionRequest):
    if MODEL is None or SCALER is None:
        raise HTTPException(status_code=503, detail="模型尚未加载完成")

    input_tensor = prepare_input(request.cycles, SCALER)
    start_time = time.perf_counter()
    with torch.no_grad():
        prediction = MODEL(input_tensor).item()
    inference_time_ms = (time.perf_counter() - start_time) * 1000

    return PredictionResponse(
        predicted_capacity_Ah=round(prediction, 6),
        input_cycles=len(request.cycles),
        inference_time_ms=round(inference_time_ms, 4),
        model_version=MODEL_VERSION,
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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("inference_api:app", host="127.0.0.1", port=8000, reload=False)
