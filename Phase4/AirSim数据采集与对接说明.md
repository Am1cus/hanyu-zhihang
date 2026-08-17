# AirSim 数据采集与系统对接说明

## 1. 本次对接目标

1. 训练“最近 30 秒遥测 → 剩余可飞时间”的 LSTM V2 原型模型；
2. 向后台连续回放遥测，演示 AirSim → Spring Boot → AI → 预警 → WebSocket → Vue 看板闭环。

AirSim 数据可以用于当前原型训练和系统演示，但不能替代后续真实无人机数据微调及最终精度验收。

## 2. 架次要求

- 当前代码的最低门槛为 **20 个相互独立的完整架次**，建议采集 30～50 架次。
- “独立架次”是指重新开始一次仿真、使用新的 `flight_id`，从起飞前/起飞开始持续记录到规定终点。
- 不能把一个长 CSV 切成 20 段冒充 20 架次，也不能仅提供 20 行数据。
- 每个架次必须飞到统一的电池终止条件，例如 SOC 降至 15% 或触发设定的低压返航阈值。
- 不要在固定 60 秒时直接停止记录；如果发生碰撞、程序报错或人工提前终止，必须记录原因，该架次不能作为正常剩余时间标签。
- 20 架次到位后按完整架次划分：14 次训练、3 次验证、3 次测试。同一架次的数据不得跨集合。

## 3. 仿真电池要求

AirSim/PX4 侧需要提供随飞行变化的电池状态，不能使用恒定的 11.4 V 或固定 SOC：

- 电压应随放电、负载和低温发生合理变化；
- 电流应随悬停、爬升、巡航、载荷和风况变化；
- SOC 应随累计耗电下降，取值范围为 0～100%；
- 电流符号统一为：**正值表示放电**；
- 建议同时输出环境温度和电池温度；
- 每个架次记录电池型号、标称容量、满电电压、截止电压等配置。

如果 AirSim 本身没有真实电池模型，可以接入 PX4/SITL 电池状态，或自行实现基于电流积分、负载和温度修正的电池模型。允许使用仿真模型，但禁止用“按时间固定线性递减的假 SOC”作为最终训练数据。

## 4. 每架次必须采集的字段

原始数据建议按 10 Hz 记录，最低不低于 5 Hz；AI 训练和系统回放时会统一重采样到 1 Hz。

| 字段名 | 单位/类型 | 要求 |
| --- | --- | --- |
| `flight_id` | 字符串 | 唯一架次编号，如 `F001` |
| `timestamp` | 秒 | 从本架次开始计时，单调递增 |
| `voltage` | V | 电池端电压，必须动态变化 |
| `current` | A | 正值表示放电 |
| `battery_level` | % | SOC，范围 0～100 |
| `ambient_temp` | ℃ | 环境温度 |
| `battery_temp` | ℃ | 电池温度，强烈建议提供 |
| `wind_speed` | m/s | 风速 |
| `wind_direction` | ° | 风向，0～360 |
| `velocity_x` | m/s | NED/世界坐标 X 速度 |
| `velocity_y` | m/s | NED/世界坐标 Y 速度 |
| `velocity_z` | m/s | NED/世界坐标 Z 速度 |
| `altitude` | m | 高度，说明采用相对高度还是海拔 |
| `latitude` | ° | 用于看板地图，可选但建议提供 |
| `longitude` | ° | 用于看板地图，可选但建议提供 |
| `payload_kg` | kg | 本架次载荷 |
| `flight_mode` | 字符串 | 如 hover、cruise、climb、return |
| `end_reason` | 字符串 | 终止原因；飞行中填 `in_flight`，最后一行填实际原因 |

推荐直接采用以下 CSV 表头：

```csv
flight_id,timestamp,voltage,current,battery_level,ambient_temp,battery_temp,wind_speed,wind_direction,velocity_x,velocity_y,velocity_z,altitude,latitude,longitude,payload_kg,flight_mode,end_reason
```

终止原因使用统一枚举：

- `battery_threshold_reached`：达到统一 SOC/低压终止阈值，属于有效正常标签；
- `battery_depleted`：仿真电池耗尽，属于有效正常标签；
- `mission_complete`：任务提前完成但电量未到阈值，单独保留，不作为电池续航终点；
- `safety_abort`：人工或安全中止；
- `collision`：碰撞；
- `system_error`：仿真或程序异常。

## 5. 最低 20 架次场景设计

不要让 20 次飞行完全相同。最低数据可按下列维度组合，并为每次仿真使用不同随机种子：

| 维度 | 建议取值 |
| --- | --- |
| 环境温度 | 0℃、-10℃、-20℃、-30℃（可增加 -40℃） |
| 风速 | 0～2、3～6、7～10 m/s |
| 载荷 | 空载、轻载、重载 |
| 航迹 | 悬停、匀速巡航、爬升后巡航、变速航线 |
| 初始 SOC | 以 100% 为主，可加入 80%、60% 场景 |

最低 20 次建议确保：

- 每个温度档至少 4 次；
- 无风/低风、中风、高风均有覆盖；
- 至少 5 次含明显爬升，至少 5 次含较大载荷；
- 训练、验证、测试集中都包含不同温度和风况，不能把某一种工况全部放在同一个集合；
- 路线、速度或随机风有变化，但电池配置和字段单位保持可追溯。

正式项目中的 200 场景仿真验证可在闭环和 V2 原型跑通后继续扩充；当前 20 次只是代码训练门槛和首轮闭环验收基线。

## 6. 文件交付格式

推荐每个架次一个 CSV：

```text
airsim_flights/
├── raw_flight_001.csv
├── raw_flight_002.csv
├── ...
├── raw_flight_020.csv
└── metadata.json
```

也可以交付一个包含 `flight_id` 字段的合并 CSV。若压缩为 ZIP，每个原始文件名应以 `raw` 或 `flight_` 开头并以 `.csv` 结尾。

`metadata.json` 建议记录：AirSim/PX4 版本、无人机型号、坐标系、采样率、电池模型与容量、终止阈值、环境设置、各架次随机种子和生成日期。原始文件交付后保持只读，不要直接在原始数据上修改或补值。

## 7. 数据质量验收

提交前请自行检查：

- 至少有 20 个唯一 `flight_id`；
- 时间戳单调递增，无重复、倒序或大段断点；
- 关键字段无空值、NaN 或无穷值；
- 每个正常架次从开始一直记录到统一电池终止条件；
- 每架次的电压、SOC、电流具有合理动态变化；
- 速度可由 `velocity_x/y/z` 计算，高度和飞行阶段相符；
- 最后一条记录有真实 `end_reason`，异常中止未伪装成正常耗尽；
- 各字段单位和坐标系在全部文件中一致；
- 20 个文件不是重复复制的数据。

收到数据后，AI 侧会运行：

```bash
.venv/bin/python Phase4/audit_airsim.py /path/to/airsim_flights.zip
```

审计通过后才会生成 1 Hz 数据集、构造 30 秒滑动窗口并训练 LSTM V2。若架次不足、缺少 SOC/结束原因或电压基本恒定，程序会拒绝训练。

## 8. 联调接口说明

看板闭环联调时，AirSim 可以直接向 Spring Boot 上报遥测，也可以先交 CSV 再由 AI 侧回放。后台接收单条遥测后会保存数据库；累计到最近 30 条 1 Hz 数据后，调用飞行时间预测接口并通过 WebSocket 推送。

Spring Boot 遥测请求示例：

```json
{
  "droneId": 2,
  "droneCode": "UAV-002",
  "latitude": 39.9042,
  "longitude": 116.4074,
  "altitude": 52.3,
  "speed": 8.4,
  "heading": 95.0,
  "voltage": 11.16,
  "current": 12.8,
  "batteryLevel": 73.5,
  "batteryTemperature": -12.0,
  "envTemperature": -20.0,
  "windSpeed": 5.2,
  "windDirection": 270.0,
  "collectTime": "2026-08-17T14:30:00"
}
```

建议按 1 Hz 向后台发送；`collectTime` 使用本地 ISO 时间，格式为 `yyyy-MM-ddTHH:mm:ss`。联调期间先确认 30 条连续数据能在看板显示，再测试低电量、低温、强风和 AI 服务离线场景。

## 9. 双方交付边界

AirSim 负责人交付：仿真场景、电池动态、至少 20 个完整架次、CSV/ZIP 和元数据说明。

AI/后台负责人完成：数据审计、1 Hz 重采样、训练/验证/测试划分、LSTM V2 训练、接口部署、遥测回放、预警及看板联调。
