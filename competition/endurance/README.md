# 直接续航预测与省电路径

2026-11-17 完成第一版。输入温度、电量和风速，直接输出预计还能飞多少分钟；同一模型用于 A* 的航段耗电和往返电量预算。

## 直接使用

双击仓库根目录的 `启动寒域智航.command`，首页即为「续航与路线」。模型随程序提供，输入实际条件后点「计算续航」。[续航与路线](http://127.0.0.1:8094/endurance)

三个主要输入为气温（℃）、当前电量（0—100%）和风速（m/s）。「更多条件」可调整平飞地速、储备电量和电池标称容量。

默认参考机型的室温容量约 1.8 Ah，平飞地速 2 m/s。以 **−20 ℃、80%、5 m/s** 为例，保留 20% 后预计可飞 **2 分 07 秒**，按同一风速估计至 0% 共 **2 分 49 秒**。示例路线的分段风场和耗电单独累计，默认预计能返回，到站剩 18.5%，低于 20% 储备。

在「示例往返路线」选择「省电路线」，可查看沿途返航界限。上述例子沿去程飞到 **120 米** 处转返，预计到站剩 **23.2%**。继续到 130 米的目标点再返航，电量将低于储备。地图标出预计折返点。

命令行（在仓库根目录，使用现有 Python 3.12 比赛环境）：

```sh
.competition-venv/bin/python -m competition.endurance --temperature -20 --battery 80 --wind 5
.competition-venv/bin/python -m competition.endurance --temperature -20 --battery 90 --wind 10 --route
```

Python 调用：

```python
from competition.endurance.model import EnduranceModel

model = EnduranceModel()
result = model.predict(temperature_c=-20, battery_percent=80, wind_speed_ms=5)
print(result["remaining_minutes"], result["usable_minutes"])
```

HTTP（现有服务接口版本 `competition-v2-api-0.4`）：

```sh
curl http://127.0.0.1:8094/api/v2/endurance/predict \
  -H 'Content-Type: application/json' \
  -d '{"temperature_c":-20,"battery_percent":80,"wind_speed_ms":5}'
```

| 接口 | 用途 |
|---|---|
| `GET /api/v2/endurance/model` | 模型参数、数据范围、版本 |
| `POST /api/v2/endurance/predict` | 直接预测分钟数 |
| `POST /api/v2/endurance/route` | 示例或自定义地图的往返规划，以及省电去程的返航界限 |
| `POST /api/v2/endurance/replan` | 从当前位置按最新地图和电量重算，决定继续、返航或备降 |

完整输入合同见 [contracts.py](contracts.py)，交互接口说明在服务的 `/docs`。`route` 支持 `grid`、`start`、`goal`、`wind_direction_deg` 和 `max_airspeed_ms`；自定义地图必须同时提供起终点。坐标 `[x,y]`，方向角 0° 表示风吹向 +x，90° 表示吹向 +y。风区按后出现的覆盖前面的；未给风区的自定义地图使用输入风速作为全图风。

### 用最新条件重规划

提交当前位置 `current`、基地 `base`、完整的当前地图 `grid` 和当前电量 `battery_percent`。可选填任务点 `goal` 和已确认可用的备降点 `alternates`。障碍或风场变化后，重新提交观测到的地图。

```sh
curl http://127.0.0.1:8094/api/v2/endurance/replan \
  -H 'Content-Type: application/json' \
  -d '{"temperature_c":-20,"battery_percent":30,"wind_speed_ms":0,"grid":{"width":7,"height":3},"current":[2,1],"base":[0,1],"goal":[6,1],"alternates":[[3,1]]}'
```

示例返回 `return_to_base`，预计回基地剩 25.7%。只有经过任务点再返回基地仍能保留储备时，才返回 `continue_to_goal`，并同时提供两段路径。返航到基地能保留储备时，优先返回基地。否则，在剩余电量可达的基地和备降点中选择预计到达电量最高的一处，备降返回 `divert`。全部不可达时返回 `no_feasible_landing`。省略 `goal` 可直接请求返航或备降。结果给出剩余航段、预计耗电和到达电量，仅用来计算规划决策。

## 模型如何算

使用现有 `Phase4/processed/airsim_capacity_dataset.csv` 的 35 个 AirSim 架次、1,702 条记录。23 架次拟合，12 架次留出；每个温度—风速组合完整留出一个架次。原数据、旧 LSTM 权重与 v2 冻结执行器均保留。

这次三个输入是当前条件，没有历史序列，因此采用**温度容量拟合 + 非负耗电回归 + 电量守恒换算**。输入改变就能计算，不需等待 30 秒窗口。

训练得到的近似关系为：

```text
当前温度满电容量 Ah = 1.800001 + 0.014400 × (min(温度, 25) − 25)
预计电流 A         = 16.998565 + 0.357611 × 风速 + 0.209130 × 平飞速度²
预计剩余分钟       = 满电容量 × 当前电量百分比 / 100 / 预计电流 × 60
预留后的可用分钟   = 满电容量 × max(当前百分比 − 预留百分比, 0) / 100 / 预计电流 × 60
```

使用自定义室温容量时，容量曲线按比例缩放，负载仍按该参考机型估计。25℃以上容量保持室温值；负温度下电池与环境温度按热平衡处理。路线折合 Wh 使用 11.1 V 标称电压，15 m/s 最大空速是路线计算的可调假设。这些参数没有被冒充为厂家给出的整机指标。

训练数据温度为 −35/−30/−25/−10℃，风速为 0/5/10 m/s，SOC 约 69—100%，运动速度 0—2.93 m/s。源 `speed_ms` 含三维运动速度，当前推理按平飞使用。模型允许正常范围内的其他输入并标记外推；没有将短日志的结束当作电池耗尽。保持工况的剩余时间换算方式可参照 [PX4 对剩余时间字段的定义](https://docs.px4.io/main/en/msg_docs/BatteryStatusV0)，模型系数来自本项目数据。

12 个留出架次的**平均电流** MAPE 为 0.9164%，固定平均电流基线为 7.1788%。这是耗电率的结果；当前没有真实耗尽标签，尚无全航程分钟误差。原始结果见 [训练结果](evidence/training-report.json) 和 [逐条留出预测](evidence/holdout-current-predictions.csv)。

重新拟合使用完整源码仓库中的数据和已有科学计算环境：

```sh
.venv/bin/python -m competition.endurance.train
```

推理文件为 [artifacts/endurance-v1.json](artifacts/endurance-v1.json)。训练脚本只使用当前电流、风速、运动速度、温度、当前容量和 SOC，不使用数据表中的未来耗电标签；留出数据未用于拟合，模型未在留出结果后调参。

## A* 改了什么

[pathfinding.py](pathfinding.py) 为同一张图预计算有向边，复用风区和功率计算。1.1 版以各行、列边界上对应方向的最低穿越耗电作为下界。走到目标至少要穿过这些边界各一次，因此这个下界仍可用来求最低耗电路径。行列边界最低价一致时，继续用方向最低价直接相乘。同优先级时优先较大已走代价，上下文内缓存重复查询。

1.1 版与 1.0 版在 18 张固定地图上比较了 1,008 次能量查询，结果均与独立 Dijkstra 一致，误差容差为 `1e-7 Wh`。分区风场的 504 次查询共展开 159,627 个节点，上一版为 274,316 个。同一 Mac 上计入构图的耗时汇总从 276 ms 降至 200 ms。无风组节点数相同，耗时为 157 ms 和 161 ms。每图每版重复 5 次，取包含构图的整组耗时中位数后汇总。

新模型根据沿途风速与实际地速给每条边计算电流，乘航行时间得到电量消耗。最大空速同时约束可维持地速的上界与下界：逆风可能减速，强顺风可能无法降至指定地速，侧风过大或无法向目标方向前进时该边不可达。去返程分别规划，比较最短距离路线与最少耗电路线。

返航界限沿已规划的省电去程逐格累计耗电，再加上各点返回基地的最低耗电。返回成本复用同一张有向图，从基地沿入边做一次最短路搜索，保留原飞行方向的风与耗电。接口与 `--route` 的 `return_limit` 给出最后一个能留足储备的点、去程距离与时间、预计到站电量，以及第一个受限点和原因。

示例的避风通道是明示的合成地图条件。−20℃、90%、10 m/s 时，省电路线往返 300 m、2.50 分钟、743.1 mAh；最短路线 260 m、2.17 分钟、773.2 mAh，省电约 3.89%。前者通过较低风速区域，因此可能飞得更久但消耗更少。上方三输入续航使用持续均匀工况，路线预算使用地图局部工况，两者不能直接只比分钟数。

1.0 版与冻结旧算法的初版对照仍保存在 [A* 基准](evidence/astar-benchmark.json)。当前往返及两类目标复用同一个规划上下文。

## 文件与本轮交付

- [实施计划](../../docs/续航预测与A星优化实施计划_20261116.md)
- [真实 HTTP 示例](evidence/http-examples.json)
- [完成记录](evidence/completion.json)
- [实际页面截图](evidence/endurance-page.jpg)
- 模型、路线和 HTTP 的 21 项针对性检查，以及原 v2 的 113 项回归通过。

新功能已经接入当前软件的独立入口。原巡看仿真的 4S1P 厂家参考曲线、执行物理模型、旧算法档案及旧复演入口仍按原版本运行，和此处约 1.8 Ah 的 AirSim 参考机型不混用。
