# 寒域智航 Phase 1：数据准备

## 阶段内容

本目录保存第一阶段的数据导出、质量检查、模拟多特征构建、特征标准化和训练数据集 V1.0。第二阶段模型脚本统一放在 `../Phase2`。

## 目录结构

```text
Phase1/
├── NASA_CSV/                 从 MATLAB 文件导出的容量数据
├── MultiFeature_CSV/         加入模拟环境特征的数据
├── figures/                  数据质量与相关性分析图
├── export_nasa_csv.py        MATLAB 容量数据导出
├── check_data_quality.py     数据质量检查
├── build_features.py         模拟多特征构建
├── standardize_and_pack.py   标准化与数据集打包
├── training_dataset_v1.csv   训练数据集 V1.0
├── scaler.pkl                特征标准化器
└── dataset_readme.md         数据集字段说明
```

## 运行顺序

在项目根目录执行：

```bash
.venv/bin/python Phase1/export_nasa_csv.py
.venv/bin/python Phase1/check_data_quality.py
.venv/bin/python Phase1/build_features.py
.venv/bin/python Phase1/standardize_and_pack.py
```

全部脚本完成后，`training_dataset_v1.csv` 和 `scaler.pkl` 可供 `Phase2` 模型训练与 `Phase3` 推理接口使用。
