# 寒域智航训练数据集 V1.0

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

共 636 条样本。

## 预处理步骤

1. 从 MATLAB `.mat` 文件中导出 NASA 电池容量数据。
2. 添加模拟极寒飞行环境特征，包括温度、风速、电压、电流和 SOC。
3. 使用 `StandardScaler` 对 `temperature_C`、`wind_speed_ms`、`voltage_V`、`current_A` 进行标准化。

## 数据质量

数据集中无缺失值、无重复行，4 块电池共 636 条样本。

## 使用说明

`soc_pct` 和 `capacity_Ah` 未进行标准化；对新数据进行同样预处理时，请使用 `Phase1/scaler.pkl` 中保存的 scaler 进行转换。
