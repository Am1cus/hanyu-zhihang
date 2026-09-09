# 寒域智航：可追溯实验演示

## 启动与回放

在 LSTM 目录执行；第一条保持运行，第二条在另一个终端执行：

```bash
./demo/start_demo.sh
./demo/replay.sh /Users/kedong/Downloads/dataset_v2.zip F022 2
```

- 入口：http://127.0.0.1:5173/ 。不自动打开浏览器可加 `--no-open`。
- 新 `dataset_v2.zip` 自动选择 **V3候选研究模式**；按manifest读原始10Hz，不把配套1Hz文件算成第二架次。旧35架次ZIP/CSV/目录继续使用V2；原始文件只读。
- `F022` 是已参与选型分析的探索性测试架次，不是新盲测。`2` 是回放倍速，`0` 为尽快回放（验收用）。首次预测需30条，首次误差需40条；2倍速下约15秒、20秒。
- `./demo/replay.sh --list /Users/kedong/Downloads/dataset_v2.zip` 显示26架次与隔离原因；4个疑似未起飞、2个异常终止禁止作正常V3回放。
- `./demo/replay.sh --list ./demo/data/collected_phase2_data.zip` 可列出全部架次。
- 旧命令 `reset_and_replay.sh` 保留兼容，但**不再删除数据库数据**。
- 新回放只切换实时视图，创建独立 run_id。相同 flight_id 多次回放也分别保存。
- `Ctrl+C` 停止启动脚本会关闭三个服务；历史记录不受影响。
- 历史视图不会跟随新回放。录制动态演示前点击“返回最新回放”。不要把停止推流后的历史状态当作故障。

旧V2演示仍可显式执行；不带参数的旧脚本默认项也保留：

```bash
./demo/replay.sh ./demo/data/collected_phase2_data.zip flight_036 2
```

## 看板新增操作

1. **历史实验**：按架次过滤，查看各次运行的样本数、有效预测数、已验证误差，打开历史曲线。历史视图不会被新架次回放切走。
2. **查看数据与模型指纹**：可查数据、预处理配置、模型与标准化器 SHA-256。
3. **复算已存窗口**：选择样本后，后台把该次保存的原始输入重新交给当前AI。核对模型/标准化器版本后比较结果，复算记录单独保存，原预测不被覆盖。一致性不代表准确率。
4. **导出完整档案**：下载本次运行的元数据、全部遥测/预测/验证结果，以及最近50条复算记录；不受图表1800条显示上限影响。推荐在回放完成后导出。
5. **V3实验验证**：真实调用冻结候选，展示LSTM、历史10秒耗电延续、过去20秒均流估算和仿真后验耗电。三个方法用相同有效窗口计算误差；无未来标签不计数。旧V2报告保留在折叠区。

## 中断后继续同一次实验

终端会输出 `run_id`，也能从历史实验中查看。使用**相同数据源、架次及预处理参数**继续：

```bash
./demo/replay.sh ./demo/data/collected_phase2_data.zip flight_036 2 --run-id 实际运行UUID
```

服务器校验数据和配置指纹；相同样本重复发送不重复入库/推理。相同序号但内容不同返回409，原记录保留。重启后仍能利用已存的29条数据接收第30条完成首个推理。没有正常封存的记录显示“未封存”，不冒充仍在飞行。

额外参数位于前三个位置参数之后，如 `--max-samples 30`。续传时需保持原参数一致，不能用改变样本数等方式改写旧实验。

## 保存位置与备份

通过一键启动脚本，演示数据库为：

```text
LSTM/.demo-runtime/data/cold-aviation.mv.db
```

直接以 Maven 启动 demo 配置时默认在后台目录 `data/cold-aviation.mv.db`；可设置 `DEMO_DATABASE_PATH` 指定无扩展名的完整路径。SQL初始化只建不存在的表/索引，不会清空旧表。

备份整个数据库应先按 Ctrl+C 停止服务，再复制该 `.mv.db` 文件到备份目录；不要直接覆盖正在运行的数据库。网页JSON导出适合单次实验审阅，不是整个数据库备份，也不提供导入还原。

升级前的内存演示记录已单独导出到：
`output/backups/legacy-demo-before-persistence-20260907.json`。
旧记录没有 run_id/数据指纹，不伪造出处混入新档案。

## 数据与推理规则

- 一次实验对应一个 flight_id 和独立 run_id。持久化每条 sourceTimeS、sampleSeq、遥测、预测输入/输出、模型指纹与后验误差。
- 1 Hz按秒取均值，不插补缺失秒；相同原始时间戳冲突会拒绝回放。源时间用于预测对齐，接收墙钟时间不参与输入指纹。
- V3一秒桶`[k,k+1)`在`k+1`才可用，保留速度与风的三轴分量；采样合同`completed_1hz_bin_means_right_boundary_v1`。新ZIP必须保留批次/架次manifest，不单独抽出CSV冒充同一候选实验。
- 连续30条才推理。缺字段、越界、时间/序号断点等会记录具体不可用原因，重新累积连续窗口；不把缺值变成0。
- 模型预测未来10秒耗电量，再用当前容量减去预测耗电量得到未来剩余容量。预测点按目标源时间+10秒对齐后续实测。
- 同一运行的目标时刻有合法容量标签才验证；容量反向增加不作有效放电标签，零耗电不计MAPE。末尾无标签预测保留为待验证。
- AI离线仍保存遥测及不可用状态，不补造结果。后来恢复AI可继续新窗口，不能事后替换原预测。
- 缺经纬度时，相对轨迹来自AirSim NED速度积分，坐标原点仅作演示；非真实地图定位/路径规划。
- 新包位置来自AirSim原点和位移近似换算，电池值来自配套公式。V3没有直接输入温度，电荷量Ah也不是低温可用能量Wh。
- 不平滑、不加噪声、不做线性校正。阈值预警并非LSTM异常识别。

## 接口概要（本机演示）

- `POST /api/runs`：创建实验元数据；返回runId和collectStartTime。
- `POST /api/telemetry`：需带runId、flightId、sampleSeq、sourceTimeS，collectTime等于实验起始时间+源时间。
- `GET /api/runs?page=1&size=10&flightId=flight_036`：历史分页，flightId可选。
- `GET /api/runs/{runId}`、`/events?afterSeq=-1&limit=1000`：元数据和游标分页事件。
- `POST /api/runs/{runId}/finish`：COMPLETED或INTERRUPTED。
- `POST /api/runs/{runId}/recheck?sampleSeq=29`、`GET .../rechecks`：窗口复算与最近50条记录。
- AI新增 `POST :8000/api/predict/energy-v3`，请求包含`drone_id`、`sampling_contract`、`data_source`及30条`samples`；冻结包`example_request.json`给出样本合同，在线调用额外提供`drone_id`。
- `GET :8000/api/models/energy-v3/report`、后台 `GET /api/dashboard/energy-v3-report`：候选说明与运行时复算证据。原 `/predict`、V2接口保留；剩余航时模型仍不可用。

本次只验收 **demo配置/H2文件数据库**。MySQL开发/生产配置尚需迁移和回归，不应直接切换。当前演示接口没有完整身份鉴权，不要暴露到公网。

## 2026-09-10 工程验收

- 20个正常架次，6,233条遥测全部保存，5,653个完整窗口均成功预测，5,453个预测有合法未来标签。每架次开头29条收集窗口、末尾10个预测缺标签，均属预期行为。
- 本机遥测HTTP平均13.91ms；后台到AI HTTP P99为8.97ms。浏览器60条上报至对应Vue DOM更新加两次动画帧，平均42.04ms、最大51.60ms。不是传感器到显示器实测，也不是树莓派指标。
- 重复请求、冲突/乱序/跨架次、缺风向/缺秒、AI暂停恢复、SOC与温度规则预警、三个服务重启恢复、历史复算与导出均检查通过。
- 验收用独立数据库`output/v3-acceptance-20260909.CnLSXA/experiments.mv.db`，没有清空原演示数据库。报告在同目录；`batch/report.json`只测接口，浏览器计时另存`browser-latency.json`。

重新验收会创建新实验，使用新的输出目录，不覆盖旧报告：

```bash
learn/.venv/bin/python learn/Phase4/accept_energy_v3.py --source /Users/kedong/Downloads/dataset_v2.zip --output output/v3-acceptance-new
```

若要重开本轮完整验收档案（不是日常默认库），在服务停止后执行：

```bash
DEMO_DATABASE_PATH=/Users/kedong/Documents/大创项目/LSTM/output/v3-acceptance-20260909.CnLSXA/experiments ./demo/start_demo.sh
```

## 模型结论与下一步

V2、标准化器和独立测试划分未变。现有5个测试架次共105个重叠窗口，10秒耗电MAPE：LSTM约1.335%，历史10秒延续基线约0.893%。这说明现有数据上LSTM还没有战胜最强简单基线，不能把演示曲线贴合当作模型优势。

V3已接通研究模式，原权重与选型记录未改动。本次20架次回放复用了现有数据，其中包含训练/验证/探索性测试；只证明工程链路，不构成新的模型确认。不要把单架次MAPE或“100%请求成功率”说成模型准确率。

下一步先请AirSim同学交付采集和电池模型源码、参数、场景配置，核查后按冻结方案采集24个新seed独立确认架次，再决定是否采用V3。详见`output/V3闭环验收-20260910/AirSim下一批交付清单.md`。当前不提供真实极寒、剩余航时或SOH结论。
