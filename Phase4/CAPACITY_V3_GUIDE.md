# AirSim 耗电 V3：训练、选型与冻结候选

本目录新增流程与原 V1/V2 服务隔离。不要覆盖 `models/airsim_capacity_lstm_v2*`，也不要把候选模型描述为完成真机、容量衰减、SOH 或剩余航程验收。

## 当前结论

- 原固定实验：`experiments/capacity_v3_20260908`。训练前冻结协议，开发集选定 `direct_full32`，它在保留数据上未通过预设推广门槛。
- 项目主模型方向：`residual_core32`，六类电流/运动/风特征，三个随机种子 FP32 集成。查看完整实验后作出的选择，性质是“待独立确认的结题候选”。
- 独立冻结包：`releases/energy_residual_lstm_v3_rc1`。冻结时未改在线部署；2026-09-10已新增候选旁路API与网页，不覆盖旧模型，也不改变冻结包内的历史声明。`MODEL_DECISION.md` 给出选择理由、全部架次和下一轮确认要求。
- 若严格确认不支持 LSTM 的实际收益，应保留树模型/简单估算作为替代方案，不能为了符合论文题目掩盖结果。

## 已完成实验的复现命令

从 `learn` 目录运行。现有路径不可覆盖，换用一个全新的输出目录才能重跑：

```sh
.venv/bin/python Phase4/train_capacity_v3.py prepare --source /Users/kedong/Downloads/dataset_v2.zip --output Phase4/experiments/my_reproduction
.venv/bin/python Phase4/train_capacity_v3.py fit --output Phase4/experiments/my_reproduction
.venv/bin/python Phase4/train_capacity_v3.py evaluate --output Phase4/experiments/my_reproduction
.venv/bin/python Phase4/report_capacity_v3.py --experiment Phase4/experiments/my_reproduction
```

重复复现不等于新盲测。模型选择只用开发数据；不能看过 test/extra 后调整参数，再把这些架次报成独立测试。

`train_capacity_v3.py` 与 `capacity_v3.py` 是首轮冻结实现，协议记录其 SHA-256。首轮 exporter 的文字字段把直接模型也描述成残差模型；报告器只更正生成清单的描述，保留 `metadata_erratum.json`。实际推理公式、权重、原模型选择和测试预测未变。不要为了消除这条记录而重写锁定实验。

## 运行已冻结的项目候选

无需再次训练：

```sh
.venv/bin/python Phase4/releases/energy_residual_lstm_v3_rc1/runtime.py --request Phase4/releases/energy_residual_lstm_v3_rc1/example_request.json
```

运行任意原数据的已完成时刻，可用研究入口：

```sh
.venv/bin/python Phase4/predict_capacity_v3.py --flight F022 --available-at 60 --candidate residual_core32
```

以上两个独立命令不会写入后台数据库。网页现已支持按实验配置显式选择V3候选：新manifest ZIP选择V3研究模式，旧数据保留V2。后台保存输入/原始输出/两种基线/后验标签；新接口`/api/predict/energy-v3`不会替换`/predict`或V2。

从LSTM目录运行 `./demo/start_demo.sh`，另一个终端运行 `./demo/replay.sh /Users/kedong/Downloads/dataset_v2.zip F022 2`；在网页“实验验证”查看四曲线与同窗口误差。F022属于已参与选型分析的探索性测试，不是新独立确认。

独立运行时只需 `numpy`、`torch`（当前验证版本 PyTorch 2.8.0），不依赖训练脚本或 sklearn。包内包含三个原始权重、JSON 标准化参数、运行时代码、文件哈希、30 秒示例输入、复算与量化诊断。JSON 中 `valid=true` 只表示本次输入满足合同且算出数值；`project_acceptance_passed=false`、`validated_on_real_data=false` 是不同层面的研究状态。

## 接口与指标口径

- 数据源限 `AIRSIM_FORMULA_BATTERY`；采样合同是 `completed_1hz_bin_means_right_boundary_v1`。
- 一秒桶 `[k,k+1)` 必须在 `k+1` 后才可用；不得把就近取样 1Hz CSV 直接冒充秒均值。
- 30 条记录均带 `flight_id`，源时间连续，不能混架次、缺秒插补、未来信息泄漏或根据文件尾生成假标签。
- 模型特征：电流、风速、水平速度、垂直速度、相对气流速度、沿运动方向风分量。
- 参考量：过去 10 秒电荷差。输出：三个 `参考量 × exp(LSTM 输出)` 的均值。没有时间方向的平滑、事后线性纠正或噪声装饰。
- 标签：两个完整平均电荷量之间的 10 秒差，不是当前 SOC 对容量的恒等换算。未来剩余电荷量仅为当前值减去预测耗电量。
- 展示误差必须标明耗电量 MAPE、窗口加权/架次等权口径、独立架次数；重叠窗口不是独立实验。
- 不合法输入返回明确原因与空预测，不返回 `-1`，不夹紧或平滑结果来制造正确曲线。

## 验证

```sh
.venv/bin/python -m unittest discover -s tests -v
```

包括因果性、跨架次隔离、缺秒处理、窗口标签、模型重载、冻结包复算、损坏权重检测和旧 V1/V2 回归测试。保留数据的成功复算仅证明工程一致性，不增加独立预测验证样本。

后续确认要使用未参与本轮开发的新采集 seed；先取得采集/电池模型代码并冻结场景配置，再执行冻结权重。确认不通过也保留结果，不在同一确认集上继续调参。

工程验收脚本：`accept_energy_v3.py`（20架次HTTP）、`accept_energy_v3_faults.py`（有明确PID校验的本机故障注入）、`accept_energy_v3_restart.py`（prepare/verify两阶段重启）。故障脚本只能指定自己启动的本机AI进程，不能用于他人的共享服务。20次重复推理与1864窗口复算均不新增独立数据。
