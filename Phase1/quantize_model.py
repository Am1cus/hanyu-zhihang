import os
import time

import numpy as np
import pandas as pd
import torch
from torch import nn


LOOKBACK = 10
TRAIN_RATIO = 0.8
TIMING_RUNS = 100
FEATURE_COLUMNS = [
    "temperature_C",
    "wind_speed_ms",
    "voltage_V",
    "current_A",
    "soc_pct",
]
TARGET_COLUMN = "capacity_Ah"
BATTERY_ORDER = ["B5", "B6", "B7", "B18"]


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


def load_dataset(dataset_path):
    data_frame = pd.read_csv(dataset_path, encoding="utf-8-sig")
    return data_frame.sort_values(["battery_id", "cycle"]).reset_index(drop=True)


def create_test_samples(data_frame):
    test_samples = []

    for battery_id in BATTERY_ORDER:
        battery_data = (
            data_frame[data_frame["battery_id"] == battery_id]
            .sort_values("cycle")
            .reset_index(drop=True)
        )
        split_index = int(len(battery_data) * TRAIN_RATIO)
        feature_values = battery_data[FEATURE_COLUMNS].to_numpy(dtype=np.float32)
        target_values = battery_data[TARGET_COLUMN].to_numpy(dtype=np.float32)

        for target_index in range(LOOKBACK, len(battery_data)):
            if target_index >= split_index:
                test_samples.append(
                    {
                        "x": feature_values[target_index - LOOKBACK : target_index],
                        "y": target_values[target_index],
                    }
                )

    return test_samples


def samples_to_tensors(samples):
    feature_values = np.array([sample["x"] for sample in samples], dtype=np.float32)
    target_values = np.array([sample["y"] for sample in samples], dtype=np.float32)
    return torch.tensor(feature_values), target_values


def calculate_mape(true_values, predicted_values):
    true_values = np.asarray(true_values, dtype=np.float64)
    predicted_values = np.asarray(predicted_values, dtype=np.float64)
    return np.mean(np.abs((true_values - predicted_values) / true_values)) * 100


def predict(model, input_tensor):
    model.eval()
    with torch.no_grad():
        return model(input_tensor).cpu().numpy().reshape(-1)


def measure_inference_time(model, input_tensor):
    model.eval()

    with torch.no_grad():
        model(input_tensor)

    start_time = time.perf_counter()
    with torch.no_grad():
        for _ in range(TIMING_RUNS):
            model(input_tensor)
    elapsed_time = time.perf_counter() - start_time

    return elapsed_time * 1000 / TIMING_RUNS


def get_file_size_kb(file_path):
    return os.path.getsize(file_path) / 1024


def print_summary(original_size_kb, quantized_size_kb, original_time_ms, quantized_time_ms, original_mape, quantized_mape):
    print("=" * 76)
    print("模型量化对比结果：")
    print(f"{'模型版本':<14}{'模型大小(KB)':>16}{'平均推理时间(ms)':>22}{'MAPE(%)':>14}")
    print("-" * 76)
    print(f"{'原始模型':<14}{original_size_kb:>16.2f}{original_time_ms:>22.4f}{original_mape:>14.4f}")
    print(f"{'量化模型':<14}{quantized_size_kb:>16.2f}{quantized_time_ms:>22.4f}{quantized_mape:>14.4f}")
    print("=" * 76)


def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(current_dir, "training_dataset_v1.csv")
    original_model_path = os.path.join(current_dir, "multi_lstm_model.pth")
    quantized_model_path = os.path.join(current_dir, "multi_lstm_model_quantized.pth")

    if not os.path.exists(dataset_path):
        raise FileNotFoundError(f"未找到训练数据集：{dataset_path}")
    if not os.path.exists(original_model_path):
        raise FileNotFoundError(f"未找到原始模型：{original_model_path}")

    torch.set_num_threads(1)
    if "qnnpack" not in torch.backends.quantized.supported_engines:
        raise RuntimeError("当前 PyTorch 环境不支持 qnnpack 动态量化后端")
    torch.backends.quantized.engine = "qnnpack"
    print(f"当前量化后端：{torch.backends.quantized.engine}")
    data_frame = load_dataset(dataset_path)
    test_samples = create_test_samples(data_frame)
    test_x, test_y = samples_to_tensors(test_samples)
    print(f"测试样本数量：{len(test_samples)}")

    original_model = MultiFeatureLSTM(input_size=len(FEATURE_COLUMNS))
    original_model.load_state_dict(torch.load(original_model_path, map_location="cpu", weights_only=True))
    original_model.eval()

    quantized_model = torch.quantization.quantize_dynamic(
        original_model,
        {nn.LSTM},
        dtype=torch.qint8,
    )
    quantized_model.eval()
    torch.save(quantized_model.state_dict(), quantized_model_path)

    original_predictions = predict(original_model, test_x)
    quantized_predictions = predict(quantized_model, test_x)
    original_mape = calculate_mape(test_y, original_predictions)
    quantized_mape = calculate_mape(test_y, quantized_predictions)

    original_time_ms = measure_inference_time(original_model, test_x)
    quantized_time_ms = measure_inference_time(quantized_model, test_x)
    original_size_kb = get_file_size_kb(original_model_path)
    quantized_size_kb = get_file_size_kb(quantized_model_path)

    print_summary(
        original_size_kb,
        quantized_size_kb,
        original_time_ms,
        quantized_time_ms,
        original_mape,
        quantized_mape,
    )
    print(f"量化模型已保存：{quantized_model_path}")
    print("模型量化完成")


if __name__ == "__main__":
    main()
