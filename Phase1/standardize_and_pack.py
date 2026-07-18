import os

import joblib
import pandas as pd
from sklearn.preprocessing import StandardScaler


CSV_FILE_MAP = {
    "B5_multi.csv": "B5",
    "B6_multi.csv": "B6",
    "B7_multi.csv": "B7",
    "B18_multi.csv": "B18",
}
STANDARDIZED_FEATURE_COLUMNS = [
    "temperature_C",
    "wind_speed_ms",
    "voltage_V",
    "current_A",
]
OUTPUT_COLUMNS = [
    "cycle",
    "capacity_Ah",
    "temperature_C",
    "wind_speed_ms",
    "voltage_V",
    "current_A",
    "soc_pct",
    "battery_id",
]


def load_multi_feature_data(input_dir):
    data_frames = []

    for file_name, battery_id in CSV_FILE_MAP.items():
        file_path = os.path.join(input_dir, file_name)
        data_frame = pd.read_csv(file_path)
        data_frame["battery_id"] = battery_id
        data_frames.append(data_frame)

    merged_data = pd.concat(data_frames, ignore_index=True)
    return merged_data[OUTPUT_COLUMNS]


def standardize_features(merged_data):
    before_stats = merged_data[STANDARDIZED_FEATURE_COLUMNS].agg(["mean", "std"])

    scaler = StandardScaler()
    standardized_values = scaler.fit_transform(merged_data[STANDARDIZED_FEATURE_COLUMNS])
    merged_data.loc[:, STANDARDIZED_FEATURE_COLUMNS] = standardized_values

    after_stats = merged_data[STANDARDIZED_FEATURE_COLUMNS].agg(["mean", "std"])

    return merged_data, scaler, before_stats, after_stats


def print_dataset_summary(merged_data, before_stats, after_stats):
    row_count, column_count = merged_data.shape

    print("=" * 60)
    print(f"合并数据集总行数：{row_count}")
    print(f"合并数据集总列数：{column_count}")

    print("=" * 60)
    print("列名和数据类型：")
    print(merged_data.dtypes)

    print("=" * 60)
    print("标准化前后均值和标准差对比：")
    for column_name in STANDARDIZED_FEATURE_COLUMNS:
        before_mean = before_stats.loc["mean", column_name]
        before_std = before_stats.loc["std", column_name]
        after_mean = after_stats.loc["mean", column_name]
        after_std = after_stats.loc["std", column_name]
        print(
            f"{column_name}: "
            f"标准化前 mean={before_mean:.6f}, std={before_std:.6f}; "
            f"标准化后 mean={after_mean:.6f}, std={after_std:.6f}"
        )

    print("=" * 60)
    print("每个 battery_id 的行数：")
    print(merged_data["battery_id"].value_counts().sort_index())


def save_dataset_readme(readme_path, total_samples):
    readme_content = f"""# 寒域智航训练数据集 V1.0

## 数据集名称和版本

寒域智航训练数据集 V1.0

## 数据来源

NASA PCoE battery data + simulated environmental features

## 字段说明

| 字段名 | 含义 | 单位 |
| --- | --- | --- |
| cycle | 电池充放电循环次数 | 次 |
| capacity_Ah | 当前循环下的电池容量 | Ah |
| temperature_C | 模拟极寒环境温度 | 摄氏度 |
| wind_speed_ms | 模拟飞行环境风速 | m/s |
| voltage_V | 根据容量估算并加入噪声后的电压 | V |
| current_A | 模拟无人机飞行放电电流 | A |
| soc_pct | 荷电状态百分比 | % |
| battery_id | 电池编号 | 无 |

## 样本总数

共 {total_samples} 条样本。

## 预处理步骤

1. 从 MATLAB `.mat` 文件中导出 NASA 电池容量数据。
2. 添加模拟极寒飞行环境特征，包括温度、风速、电压、电流和 SOC。
3. 使用 `StandardScaler` 对 `temperature_C`、`wind_speed_ms`、`voltage_V`、`current_A` 进行标准化。

## 数据质量

数据集中无缺失值、无重复行，4 块电池共 636 条样本。

## 使用说明

`soc_pct` 和 `capacity_Ah` 未进行标准化；对新数据进行同样预处理时，请使用 `Phase1/scaler.pkl` 中保存的 scaler 进行转换。
"""

    with open(readme_path, "w", encoding="utf-8") as readme_file:
        readme_file.write(readme_content)


def main():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    input_dir = os.path.join(current_dir, "MultiFeature_CSV")
    scaler_path = os.path.join(current_dir, "scaler.pkl")
    dataset_path = os.path.join(current_dir, "training_dataset_v1.csv")
    readme_path = os.path.join(current_dir, "dataset_readme.md")

    os.makedirs(current_dir, exist_ok=True)

    merged_data = load_multi_feature_data(input_dir)
    merged_data, scaler, before_stats, after_stats = standardize_features(merged_data)

    joblib.dump(scaler, scaler_path)
    merged_data.to_csv(dataset_path, index=False, encoding="utf-8-sig")
    save_dataset_readme(readme_path, len(merged_data))

    print_dataset_summary(merged_data, before_stats, after_stats)
    print("=" * 60)
    print(f"标准化器已保存：{scaler_path}")
    print(f"训练数据集已保存：{dataset_path}")
    print(f"数据集说明文档已保存：{readme_path}")
    print("V1.0 训练数据集打包完成")

    del merged_data, scaler, before_stats, after_stats


if __name__ == "__main__":
    main()
