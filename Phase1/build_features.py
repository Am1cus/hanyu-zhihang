import os

current_file_dir = os.path.dirname(os.path.abspath(__file__))
matplotlib_cache_dir = os.path.join(current_file_dir, "matplotlib_cache")
os.makedirs(matplotlib_cache_dir, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", matplotlib_cache_dir)

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


RANDOM_SEED = 42
CSV_FILE_MAP = {
    "B5_capacity.csv": "B5_multi.csv",
    "B6_capacity.csv": "B6_multi.csv",
    "B7_capacity.csv": "B7_multi.csv",
    "B18_capacity.csv": "B18_multi.csv",
}
HEATMAP_LABELS = {
    "cycle": "循环次数",
    "capacity_Ah": "容量",
    "temperature_C": "温度",
    "wind_speed_ms": "风速",
    "voltage_V": "电压",
    "current_A": "电流",
    "soc_pct": "荷电状态",
}


def set_chinese_font():
    plt.rcParams["font.sans-serif"] = [
        "Arial Unicode MS",
        "SimHei",
        "Heiti TC",
        "Microsoft YaHei",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def create_temperature(row_count):
    temperature_values = np.random.normal(loc=-27, scale=1.5, size=row_count)
    return np.clip(temperature_values, -30, -25)


def create_wind_speed(row_count):
    wind_speed_values = np.random.exponential(scale=3, size=row_count)
    return np.clip(wind_speed_values, 0, 12)


def create_voltage(capacity_series, initial_capacity):
    voltage_noise = np.random.normal(loc=0, scale=0.02, size=len(capacity_series))
    return 14.0 + (capacity_series / initial_capacity) * 2.8 + voltage_noise


def create_current(row_count):
    current_noise = np.random.normal(loc=0, scale=0.3, size=row_count)
    return 8.0 + current_noise


def build_multi_feature_data(data_frame):
    row_count = len(data_frame)
    initial_capacity = data_frame["capacity_Ah"].iloc[0]

    multi_feature_data = pd.DataFrame(
        {
            "cycle": data_frame["cycle"],
            "capacity_Ah": data_frame["capacity_Ah"],
            "temperature_C": create_temperature(row_count),
            "wind_speed_ms": create_wind_speed(row_count),
            "voltage_V": create_voltage(data_frame["capacity_Ah"], initial_capacity),
            "current_A": create_current(row_count),
            "soc_pct": (data_frame["capacity_Ah"] / initial_capacity) * 100,
        }
    )

    return multi_feature_data


def save_multi_feature_files(csv_dir, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    for input_file_name, output_file_name in CSV_FILE_MAP.items():
        input_file_path = os.path.join(csv_dir, input_file_name)
        output_file_path = os.path.join(output_dir, output_file_name)

        data_frame = pd.read_csv(input_file_path)
        multi_feature_data = build_multi_feature_data(data_frame)
        multi_feature_data.to_csv(output_file_path, index=False)

        row_count, column_count = multi_feature_data.shape
        print(f"已保存 {output_file_name}，共 {row_count} 行，{column_count} 列")


def print_correlation_ranking(b5_multi_path):
    data_frame = pd.read_csv(b5_multi_path)
    correlation_series = data_frame.corr(numeric_only=True)["capacity_Ah"]
    sorted_correlations = (
        correlation_series.drop("capacity_Ah").reindex(
            correlation_series.drop("capacity_Ah").abs().sort_values(ascending=False).index
        )
    )

    print("与容量最相关的特征排序：")
    for feature_name, correlation_value in sorted_correlations.items():
        print(f"{feature_name}: {correlation_value:.6f}")

    return data_frame.corr(numeric_only=True)


def save_correlation_heatmap(correlation_matrix, figures_dir):
    os.makedirs(figures_dir, exist_ok=True)

    labels = [HEATMAP_LABELS.get(column_name, column_name) for column_name in correlation_matrix.columns]

    plt.figure(figsize=(9, 7))
    image = plt.imshow(correlation_matrix, cmap="coolwarm", vmin=-1, vmax=1)
    plt.colorbar(image, fraction=0.046, pad=0.04)
    plt.xticks(range(len(labels)), labels, rotation=45, ha="right")
    plt.yticks(range(len(labels)), labels)
    plt.title("极寒飞行多特征相关性分析")

    for row_index in range(len(labels)):
        for column_index in range(len(labels)):
            value = correlation_matrix.iloc[row_index, column_index]
            text_color = "white" if abs(value) > 0.6 else "black"
            plt.text(
                column_index,
                row_index,
                f"{value:.2f}",
                ha="center",
                va="center",
                color=text_color,
                fontsize=9,
            )

    plt.tight_layout()
    output_path = os.path.join(figures_dir, "correlation_heatmap.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print(f"相关性热力图已保存：{output_path}")


def main():
    np.random.seed(RANDOM_SEED)
    set_chinese_font()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_dir = os.path.join(current_dir, "NASA_CSV")
    output_dir = os.path.join(current_dir, "MultiFeature_CSV")
    figures_dir = os.path.join(current_dir, "figures")

    save_multi_feature_files(csv_dir, output_dir)

    b5_multi_path = os.path.join(output_dir, "B5_multi.csv")
    correlation_matrix = print_correlation_ranking(b5_multi_path)
    save_correlation_heatmap(correlation_matrix, figures_dir)
    print("多特征数据构建完成")


if __name__ == "__main__":
    main()
