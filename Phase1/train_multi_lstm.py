import os
import random

from sympy import true

current_file_dir = os.path.dirname(os.path.abspath(__file__))
matplotlib_cache_dir = os.path.join(current_file_dir, "matplotlib_cache")
os.makedirs(matplotlib_cache_dir, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", matplotlib_cache_dir)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset


RANDOM_SEED = 42
LOOKBACK = 10
TRAIN_RATIO = 0.8
BATCH_SIZE = 32
EPOCHS = 300
LEARNING_RATE = 0.001
FEATURE_COLUMNS = [
    "temperature_C",
    "wind_speed_ms",
    "voltage_V",
    "current_A",
    "soc_pct",
]
TARGET_COLUMN = "capacity_Ah"
BATTERY_ORDER = ["B5", "B6", "B7", "B18"]
BATTERY_COLORS = {
    "B5": "#1f77b4",
    "B6": "#ff7f0e",
    "B7": "#2ca02c",
    "B18": "#9467bd",
}


def set_random_seed(seed):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def set_chinese_font():
    plt.rcParams["font.sans-serif"] = [
        "Arial Unicode MS",
        "SimHei",
        "Heiti TC",
        "Microsoft YaHei",
    ]
    plt.rcParams["axes.unicode_minus"] = False


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
        predictions = self.output_layer(last_time_step)
        return predictions


def load_dataset(dataset_path):
    data_frame = pd.read_csv(dataset_path, encoding="utf-8-sig")
    return data_frame.sort_values(["battery_id", "cycle"]).reset_index(drop=True)


def create_time_series_samples(data_frame):
    train_samples = []
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
        cycle_values = battery_data["cycle"].to_numpy(dtype=np.int64)

        for target_index in range(LOOKBACK, len(battery_data)):
            sample = {
                "x": feature_values[target_index - LOOKBACK : target_index],
                "y": target_values[target_index],
                "battery_id": battery_id,
                "cycle": cycle_values[target_index],
            }

            if target_index < split_index:
                train_samples.append(sample)
            else:
                test_samples.append(sample)

    return train_samples, test_samples


def samples_to_tensors(samples):
    x_values = np.array([sample["x"] for sample in samples], dtype=np.float32)
    y_values = np.array([sample["y"] for sample in samples], dtype=np.float32).reshape(-1, 1)

    x_tensor = torch.tensor(x_values, dtype=torch.float32)
    y_tensor = torch.tensor(y_values, dtype=torch.float32)

    return x_tensor, y_tensor


def train_model(model, train_loader, device):
    loss_function = nn.MSELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=LEARNING_RATE)

    model.train()
    for epoch in range(1, EPOCHS + 1):
        total_loss = 0.0

        for batch_x, batch_y in train_loader:
            batch_x = batch_x.to(device)
            batch_y = batch_y.to(device)

            optimizer.zero_grad()
            predictions = model(batch_x)
            loss = loss_function(predictions, batch_y)
            loss.backward()
            optimizer.step()

            total_loss += loss.item() * len(batch_x)

        average_loss = total_loss / len(train_loader.dataset)
        if epoch == 1 or epoch % 50 == 0:
            print(f"第 {epoch:03d} 轮训练损失：{average_loss:.8f}")


def predict(model, x_tensor, device):
    model.eval()
    with torch.no_grad():
        predictions = model(x_tensor.to(device)).cpu().numpy().reshape(-1)
    return predictions


def calculate_metrics(true_values, predicted_values):
    true_values = np.asarray(true_values, dtype=np.float64)
    predicted_values = np.asarray(predicted_values, dtype=np.float64)

    mae = np.mean(np.abs(true_values - predicted_values))
    mape = np.mean(np.abs((true_values - predicted_values) / true_values)) * 100

    return mae, mape


def build_results_frame(test_samples, predictions):
    return pd.DataFrame(
        {
            "battery_id": [sample["battery_id"] for sample in test_samples],
            "cycle": [sample["cycle"] for sample in test_samples],
            "true_capacity": [sample["y"] for sample in test_samples],
            "predicted_capacity": predictions,
        }
    )


def print_evaluation_table(results_frame):
    all_mae, all_mape = calculate_metrics(
        results_frame["true_capacity"], results_frame["predicted_capacity"]
    )

    print("=" * 72)
    print("测试集评估结果：")
    print(f"{'电池':<10}{'样本数':>8}{'MAE(Ah)':>16}{'MAPE(%)':>16}")
    print("-" * 72)
    print(f"{'全部':<10}{len(results_frame):>8}{all_mae:>16.6f}{all_mape:>16.4f}")

    for battery_id in BATTERY_ORDER:
        battery_results = results_frame[results_frame["battery_id"] == battery_id]
        mae, mape = calculate_metrics(
            battery_results["true_capacity"], battery_results["predicted_capacity"]
        )
        print(f"{battery_id:<10}{len(battery_results):>8}{mae:>16.6f}{mape:>16.4f}")

    print("=" * 72)


def plot_battery_results(results_frame, figures_dir):
    os.makedirs(figures_dir, exist_ok=True)

    figure, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes = axes.flatten()

    for axis, battery_id in zip(axes, BATTERY_ORDER):
        battery_results = results_frame[results_frame["battery_id"] == battery_id].sort_values("cycle")
        mae, mape = calculate_metrics(
            battery_results["true_capacity"], battery_results["predicted_capacity"]
        )

        axis.plot(
            battery_results["cycle"],
            battery_results["true_capacity"],
            color="blue",
            linewidth=2,
            label="真实容量",
        )
        axis.plot(
            battery_results["cycle"],
            battery_results["predicted_capacity"],
            color="red",
            linestyle="--",
            linewidth=2,
            label="预测容量",
        )
        axis.set_title(f"{battery_id} 测试集预测结果（MAPE={mape:.2f}%）")
        axis.set_xlabel("循环次数")
        axis.set_ylabel("容量（Ah）")
        axis.grid(True, linestyle="--", alpha=0.4)
        axis.legend()

    plt.tight_layout()
    output_path = os.path.join(figures_dir, "multi_lstm_results.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"分电池预测结果图已保存：{output_path}")


def plot_prediction_scatter(results_frame, figures_dir):
    os.makedirs(figures_dir, exist_ok=True)

    plt.figure(figsize=(8, 7))

    for battery_id in BATTERY_ORDER:
        battery_results = results_frame[results_frame["battery_id"] == battery_id]
        plt.scatter(
            battery_results["true_capacity"],
            battery_results["predicted_capacity"],
            label=battery_id,
            color=BATTERY_COLORS[battery_id],
            alpha=0.8,
        )

    min_value = min(results_frame["true_capacity"].min(), results_frame["predicted_capacity"].min())
    max_value = max(results_frame["true_capacity"].max(), results_frame["predicted_capacity"].max())
    plt.plot([min_value, max_value], [min_value, max_value], color="black", linestyle="--", label="y=x")

    plt.title("Multi-Feature LSTM Prediction (Test Set)")
    plt.xlabel("真实容量（Ah）")
    plt.ylabel("预测容量（Ah）")
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.legend()
    plt.tight_layout()

    output_path = os.path.join(figures_dir, "multi_lstm_scatter.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"预测散点图已保存：{output_path}")


def count_model_parameters(model):
    return sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)


def main():
    set_random_seed(RANDOM_SEED)
    set_chinese_font()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    dataset_path = os.path.join(current_dir, "training_dataset_v1.csv")
    figures_dir = os.path.join(current_dir, "figures")
    model_path = os.path.join(current_dir, "multi_lstm_model.pth")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"当前训练设备：{device}")

    data_frame = load_dataset(dataset_path)
    train_samples, test_samples = create_time_series_samples(data_frame)
    print(f"训练样本数量：{len(train_samples)}")
    print(f"测试样本数量：{len(test_samples)}")

    train_x, train_y = samples_to_tensors(train_samples)
    test_x, _ = samples_to_tensors(test_samples)

    train_dataset = TensorDataset(train_x, train_y)
    train_loader = DataLoader(train_dataset, batch_size=BATCH_SIZE, shuffle=True)

    model = MultiFeatureLSTM(input_size=len(FEATURE_COLUMNS)).to(device)
    parameter_count = count_model_parameters(model)
    print(f"模型可训练参数数量：{parameter_count}")

    train_model(model, train_loader, device)

    predictions = predict(model, test_x, device)
    results_frame = build_results_frame(test_samples, predictions)

    print_evaluation_table(results_frame)
    plot_battery_results(results_frame, figures_dir)
    plot_prediction_scatter(results_frame, figures_dir)

    torch.save(model.state_dict(), model_path)
    print(f"模型已保存：{model_path}")
    print("多特征 LSTM 训练完成")


if __name__ == "__main__":
    main()
