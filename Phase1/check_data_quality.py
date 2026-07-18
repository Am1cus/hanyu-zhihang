import os

current_file_dir = os.path.dirname(os.path.abspath(__file__))
matplotlib_cache_dir = os.path.join(current_file_dir, "matplotlib_cache")
os.makedirs(matplotlib_cache_dir, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", matplotlib_cache_dir)

import matplotlib.pyplot as plt
import pandas as pd


BATTERY_LABELS = {
    "B5_capacity.csv": "B5",
    "B6_capacity.csv": "B6",
    "B7_capacity.csv": "B7",
    "B18_capacity.csv": "B18",
}


def set_chinese_font():
    plt.rcParams["font.sans-serif"] = [
        "Arial Unicode MS",
        "SimHei",
        "Heiti TC",
        "Microsoft YaHei",
    ]
    plt.rcParams["axes.unicode_minus"] = False


def print_file_quality(csv_file_path):
    data_frame = pd.read_csv(csv_file_path)
    file_name = os.path.basename(csv_file_path)

    print("=" * 50)
    print(f"文件名：{file_name}")
    print(f"总行数：{data_frame.shape[0]}")
    print(f"总列数：{data_frame.shape[1]}")
    print("各列缺失值数量：")
    print(data_frame.isnull().sum())
    print(f"重复行数量：{data_frame.duplicated().sum()}")

    capacity_series = data_frame["capacity_Ah"]
    print("capacity_Ah 基本统计：")
    print(f"最小值：{capacity_series.min():.6f}")
    print(f"最大值：{capacity_series.max():.6f}")
    print(f"平均值：{capacity_series.mean():.6f}")
    print(f"中位数：{capacity_series.median():.6f}")

    return data_frame


def plot_capacity_curves(csv_dir, figures_dir):
    plt.figure(figsize=(10, 6))

    for csv_file_name, battery_label in BATTERY_LABELS.items():
        csv_file_path = os.path.join(csv_dir, csv_file_name)
        data_frame = pd.read_csv(csv_file_path)
        plt.plot(
            data_frame["cycle"],
            data_frame["capacity_Ah"],
            label=battery_label,
            linewidth=2,
        )

    plt.title("NASA Li-ion Battery Capacity Degradation Comparison")
    plt.xlabel("循环次数")
    plt.ylabel("容量（Ah）")
    plt.legend()
    plt.grid(True, linestyle="--", alpha=0.4)
    plt.tight_layout()

    os.makedirs(figures_dir, exist_ok=True)
    output_path = os.path.join(figures_dir, "all_batteries_degradation.png")
    plt.savefig(output_path, dpi=300)
    plt.close()

    print("=" * 50)
    print(f"容量衰减对比图已保存：{output_path}")


def main():
    set_chinese_font()

    current_dir = os.path.dirname(os.path.abspath(__file__))
    csv_dir = os.path.join(current_dir, "NASA_CSV")
    figures_dir = os.path.join(current_dir, "figures")

    csv_file_names = sorted(
        file_name for file_name in os.listdir(csv_dir) if file_name.endswith(".csv")
    )

    for csv_file_name in csv_file_names:
        csv_file_path = os.path.join(csv_dir, csv_file_name)
        print_file_quality(csv_file_path)

    plot_capacity_curves(csv_dir, figures_dir)
    print("数据质量检查完成")


if __name__ == "__main__":
    main()
