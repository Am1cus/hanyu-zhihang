# 寒域智航 Phase 2：模型研发与量化

## 阶段内容

本目录保存第二阶段的多特征 LSTM 训练、动态量化、预测结果图和初步验证报告。训练数据集与标准化器由 `Phase1` 提供。

## 目录结构

```text
Phase2/
├── figures/                         模型预测结果图
├── train_multi_lstm.py              多特征 LSTM 训练脚本
├── quantize_model.py                动态量化与对比脚本
├── multi_lstm_model.pth             原始模型权重
├── multi_lstm_model_quantized.pth   量化模型权重
├── model_validation_report.md       模型初步验证报告
└── README.md                        本阶段说明
```

## 运行顺序

在项目根目录执行：

```bash
.venv/bin/python Phase2/train_multi_lstm.py
.venv/bin/python Phase2/quantize_model.py
```

训练脚本自动读取 `Phase1/training_dataset_v1.csv`，生成原始模型和预测结果图；量化脚本读取原始模型并生成量化模型及对比指标。

## 当前结果

- 原始模型整体测试集 MAPE：6.4973%
- 量化模型整体测试集 MAPE：6.9465%
- 模型体积：204.69 KB 降至 62.62 KB
- 量化后体积减少约 69.4%

当前结果基于 NASA 电池容量数据和模拟环境特征，用于验证训练与量化流程。AirSim 正式仿真验证仍需使用后续规范化的仿真飞行数据完成。
