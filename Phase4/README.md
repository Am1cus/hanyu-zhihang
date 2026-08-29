# Phase 4：AirSim容量预测闭环与飞行时门禁

本目录提供AirSim数据审计、未来10秒耗电量LSTM、飞行时间数据集门禁和遥测回放工具。现有NASA容量模型V1保留在`Phase2`，不会被覆盖。

## 最新数据结论

最新AirSim压缩包包含35个独立架次和20,222条记录，覆盖-10℃、-25℃、-30℃、-35℃以及0、5、10m/s风速。电压、电流、SOC、油门和转速均有动态变化，数据质量较上一版明显提高。

当前数据仍缺少每架次真实的`end_reason`，固定约60秒结束的文件不能直接当作“剩余可飞时间”标签。因此V2训练门禁仍保持关闭；这些数据现阶段可用于工况影响分析和AirSim初步验证报告。

## AirSim容量LSTM V2

- 输入：最近30秒的温度、风速、电压、电流、SOC、速度和高度。
- 目标：未来10秒耗电量，再从当前实测容量中扣除得到未来容量。
- 验证：按完整架次划分训练、验证和测试集；量化模型耗电量MAPE为1.34%，R²为0.957。
- 边界：数据来源为AirSim仿真，不代表真实无人机精度。输出不进行曲线平滑或线性校准。

## 使用方法

```bash
.venv/bin/python Phase4/audit_airsim.py /path/to/airsim_data.zip
.venv/bin/python Phase4/prepare_airsim_capacity_dataset.py /path/to/airsim_data.zip
.venv/bin/python Phase4/train_airsim_capacity_lstm.py
.venv/bin/python Phase4/prepare_flight_time_dataset.py /path/to/qualified_data
.venv/bin/python Phase4/train_flight_time_lstm.py
.venv/bin/python Phase4/replay_airsim.py /path/to/airsim_data.zip --speed 10
```

合格数据至少需要20个独立架次、SOC/电量字段、真实结束原因以及随飞行变化的电压数据。压缩包中的原始文件可以使用`raw*.csv`或`flight_*.csv`命名。
