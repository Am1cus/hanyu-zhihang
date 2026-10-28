# 接口、开发地图与记录合同 0.3

版本：competition-v2-contract-0.3；合同日期：2026-10-11；执行接口更新：2026-10-20。四方法与参考仿真执行已接通，当前运行说明见[DAY20.md](DAY20.md)。两份公开资料需求核对已保存，真人访谈按用户指示暂缓；业务决定见[任务规格0.3](TASK_SPEC_0_3.md)，分值等继续保持假设标签。

## 10月11日历史复核入口

在 `learn` 下使用原有 Python 3.12 比赛环境，无新增依赖：

```bash
.competition-venv/bin/python -m competition.v2.tools.prepare_day11 --output ../output/4C/v2/day11 --verified-on 2026-10-13
```

本次为10月11日工作项，最终复核日期为2026-10-13；以后重跑应填写实际复核日期。10月11日首轮结果已保存在`output/4C/v2/day11/checkpoint-20261011/`。


Windows 对应将 `.competition-venv/bin/python` 改为 `.competition-venv\Scripts\python.exe`。本轮未在 Windows 实际重跑。

该命令输出五份JSON Schema、两图输入/有向航段/单点预算、六类开发检查、来源及历史文件核对和测试记录。给定顺序的决策示例只检查记录格式，不是算法选点结果；该历史命令不计正式执行。当前1,152项固定条件比较见DAY22.md。

## 数据如何流动

```mermaid
flowchart LR
  A[场景：含预设未来事件] --> B[执行侧：只应用已发生事件]
  B --> C[当前观测：无未来队列]
  C --> D[有向航段表]
  D --> E[给定任务顺序的预算核算]
  E --> F[可行、预算不足或信息不足]
```

`scenarios.py` 属于执行侧的场景准备层；算法只接收 `DecisionRequest`。未来事件在场景文件中保存便于复现，但不进入决策请求。测试会修改未来事件，检查起始决策请求的内容和哈希是否仍相同；在请求的各层注入未来队列会被拒绝。

实际运行时的位置和 Wh 必须由执行器提供。`initial_request()` 仅生成起飞前输入；`observed_grid()` 仅投影已观测地图，不推进飞机、不扣耗能。不能把晚时刻地图配上初始剩余能量冒充完整执行状态。

## 核心字段

| 对象 | 字段与含义 | 校验 |
|---|---|---|
| Task | 原字段加 `service_level / action_semantics` | 两项必填且无默认，分别只允许optional_supplemental_observation、simulated_dwell_only；不接必检或配送 |
| GridMap | 网格、风、禁入格子，加 `blocked_cell_meaning` | 必填fixed_altitude_2d_exclusion_area，地面积雪不自动等于空中障碍 |
| Observation | `as_of_s / position / base / known_map / known_map_sha256 / available_wh_estimate / temperature_c / completed_task_ids / data_status / unavailable_reason` | 坐标在图内；已完成ID必须存在；地图哈希一致；缺能量/超温度范围不可声称 AVAILABLE |
| PlanningModel | `airspeed_ms / estimated_power_w / curve_sha256 / estimator / source` | 数值有限且为正；参考曲线来源明确；固定功率×当前观测时间 |
| BudgetPolicy | `mode / reserve_wh / available_fraction_error / cost_fraction_error / parameter_source` | 可用误差在[0,1)，成本误差非负；储备只计算一次 |
| DecisionRequest | 上述观测、任务、模型、预算，加 `selector_id / contract_version` | 拒绝未知字段；没有未来事件、未来遥测和执行器真值字段 |
| LegEstimate | `from_id / to_id / status / path / distance_m / duration_s / energy_wh / reason` | 不可达时三项数值为null且路径为空；不能以0 Wh冒充不可达 |
| BudgetAssessment | 顺序、航行/停留/返程/储备、判断能量/需求/余量、状态和原因 | 余量与减法一致；UNAVAILABLE不显示数值需求；`execution_verified`恒为false |
| DecisionRecord | 请求哈希、时刻、策略、动作、顺序、未选点与原因、预算、计算毫秒 | 接受或导出前必须与请求配对校验；不能添加returned=true |
| DeferredTask | `id / reason / follow_up_state` | 仅未选点；必填REQUIRES_OPERATOR_REVIEW，不能表示已接单或COMPLETED |

节点 ID `BASE` / `CURRENT` 保留给基地和当前位置；其他为任务 ID。即使两者位置相同，也保留方向明确的键。航段表包含有序对，不能默认 `C→BASE` 等于 `BASE→C`。已完成任务不进入待选节点，也不能再次计分。

当前决策输入的位置限定为网格节点。D4 的连续执行位置另存；若事件发生在航段内部，执行器必须处理事件时刻、当前航段及下一次可决策节点，不能四舍五入跳格。阻断正在执行航段的边界情况必须明确记录失败/处置；D2的探针选用32秒测试条件；D4现已增加航段内部事件、占用航段失败与不瞬移检查。

## 接口分工

| Python 入口 | 当前状态 | 下一阶段怎么使用 |
|---|---|---|
| `development_scenarios()` | 已实现，校验两张开发地图 | D3读取任务规格，D4持有未来事件 |
| `initial_request(...)` | 已实现，参考温度与估计偏差映射到起始观测 | 开发/测试入口，不作为运行中状态恢复 |
| `observed_grid(scenario, as_of_s)` | 已实现，只投影已发生事件 | 执行侧使用，不传整个scenario给选点算法 |
| `build_leg_table(request)` | 已实现，复用v1的无状态有向A* | D3只看当前地图的航段代价 |
| `assess_order(request, legs, order)` | 已实现，判断指定顺序及返程 | D3求解器及简单策略共用相同口径 |
| `validate_decision_for_request(request, record)` | 已实现，请求配对、目录完整与预算算式校验 | D3返回结果前必须调用；不证明执行或路径最优 |
| `decide(request) -> DecisionRecord` | **已实现，selectors-0.1** | 三种基线与子集动态规划，共用当前观测、航段和预算；实际返回待执行器验证 |
| v2 HTTP运行接口、状态查询、事件与复演 | **已实现，runtime-0.1** | 本机8094，独立v2数据库，200毫秒状态查询 |

航段统一按当前风场时间/能量代价规划。`nearest_feasible` 将按这张共用航段表的 `distance_m` 选择距离较小的可行目标；不另换一种航段规划器。这是对D1“最近”口径的明确，不等同于无风曼哈顿距离。D1的教学计算器只检验抽象例，不当作网格基线代码。

## 两张开发地图

| 地图 | 规模 | 准备检验什么 |
|---|---|---|
| dev-snowfield-5 | 14×11，5点，中部局部障碍及逆风区 | 普通近点与重要远点的取舍；有方向的返程；低温预算变化 |
| dev-two-gates-8 | 18×13，8点，隔断上留两个通道 | 通道封闭后改走另一路；两条都封闭时不可达；东区风变化 |

两者每格80米，固定空速5 m/s、停留10秒、高度标注40米；这些是仿真假设，不是真实景区测绘或设备指标。源文件 `data/development_scenarios.json`，探针条件在 `data/development_probes.json`。

D2历史动态检查预先指定去C的路径，按事件前计划推算32秒时的网格位置，再从同一位置比较变化前后的路线。检查的是规划响应，没有实际运行轨迹或原始V/I/t。因此只报告“计划航段更长/不可达/能量估计改变”，不报告“无人机实际绕行并返回”。

保留集仍未生成。这两张图已被开发和检查使用，后续不得把它们称为未见测试地图。也不以这两个例子的效果作为国奖竞争力或算法泛化结论。

## 参数和记录来源

`data/parameter_sources.json` 把厂家参考、参考条件、派生估计、仿真假设和待核对需求分开。准备脚本核对保存的原PDF及曲线数据哈希，并检查场景/预算/偏差设置与登记值一致。没有新增厂家数据下载或真实校准。

55%初始SOC表示剩余Ah比例；曲线积分得到Wh，两者不能直接等比例互换。储备固定为23℃满电参考Wh的20%；改变温度不会同步缩小储备。温度超出−20至23℃时输出数据不足。原参考文件整体缺失时，起始输入构造明确失败，不捏造一个0Wh储备继续算。

## D4档案字段（现已实现）

- 配置：合同/核心/场景/参数版本、来源、温度、初始状态、策略、误差配置、种子、运行ID；私有预设事件只在完整档案中保存。
- 观测/决策：时间、当前位置、当时可见地图哈希、请求哈希、候选/放弃任务、预算和原因；决策不得反读档案中的未来事件。
- 事件：计划/实际应用时刻、内容、来源、是否应用、是否影响路径/预算；“已应用”与“有效改变行为”分别记录。
- 执行：V、I、dt、Ah、Wh、连续位置、任务停留开始/结束和完成点；终态的returned必须由到达基地判定。
- 审计：创建、暂停/恢复、取消、导出快照和复演来源；UUID、CPU耗时、墙钟与确定性结果分开。

所有实现必须区分“预算可行”“规划了返回”“实际到达基地”。D2输出里的 `execution_verified=false` 是这条边界的程序约束。

## 0.3迁移与配对边界

记录自身校验不能替代请求配对。已完成、已选待做、未选待处理必须完整覆盖目录且互不重叠；请求哈希、时刻、策略、预算模式必须匹配。REFUSED只允许当前位置在基地，ALL_TASKS_VISITED不能还留未完成点；储备和预算算式须与请求一致。

0.2请求因版本和必填字段变化会被拒绝，不静默补成“可延期”。旧源码在output/4C/v2/day11/before/source，原day2结果保留。D4持久化服务使用上述配对边界，运行库与v1分开。

## 10月13日实现补充（10月18日复核）

`selectors.decide(request)` 构建有向航段表并返回完整记录，`select_order(request, legs)` 是供受控静态测试使用的纯选点入口。`reference.brute_force_reference(request, legs=None)` 独立枚举全部有序子集，不调用求解器或预算核算函数；共用A*航段表，所以核对范围是任务选择与预算，不是独立验证A*或电化学模型。

全部方法使用 `LOWER_VALUE_PLAN` 表示“单点可行，但当前策略未选”；展示译为“当前策略未纳入本趟安排”，不能解释成该点不重要。`BUDGET`和`UNREACHABLE`以当前状态单点往返检查确定。任务经过但未停留不计计划访问。

求解能量用严格浮点值排序、相等再按完整ID序列；可行性容差为1e-7 Wh，独立核对比较价值和能量误差。计算时间包括建图与选择，确定性比较仅排除`computation_ms`。本轮记录有自己的选择器版本与源码哈希，数据合同仍为0.3。

## D4实际HTTP接口（2026-10-20）

本机地址 `http://127.0.0.1:8094`；只监听回环地址。`api.py` 提供页面与JSON，`runtime.py` 持有执行状态；选择器只接收当前观测。数据库位于工作区 `output/4C/v2/runtime/missions-v2.sqlite3`。

| 方法与路径 | 用途 |
|---|---|
| GET `/api/v2/health` | 来源、执行版本、曲线可用性 |
| POST `/api/v2/preview` | 初始方案；不创建档案，不运行 |
| POST `/api/v2/runs` | 创建运行；旧的运行自动暂停并审计 |
| GET `/api/v2/runs` | 已保存运行摘要 |
| GET `/api/v2/runs/{id}` | 执行位置、轨迹、最新预算、全部决策/事件及摘要 |
| POST `/api/v2/runs/{id}/control` | `action: pause / resume / cancel` |
| POST `/api/v2/runs/{id}/events` | `kind: obstacle_ahead / gust / both_gates` |
| GET `/api/v2/runs/{id}/export` | 配置、版本/源码/曲线指纹、原始遥测、决策与操作审计 |
| POST `/api/v2/runs/{id}/replay` | 按原配置从头复演，保存来源运行ID |

创建/预览接收 `preset, selector_id, temperature_c, initial_soc, budget_mode, speedup`，拒绝未知字段。`low_budget` 固定10%剩余Ah，`unavailable` 固定−30℃；响应状态记录实际采用的条件。六种预设见页面和DAY20.md。返回404表示无记录，409表示当前状态不能操作，422表示输入合同不符。

服务按现实时间推进仿真，执行器使用0.5秒规范步长，并精确分割曲线节点、事件、到点和停留结束。播放倍速不改积分结果。手动事件排入下一个规范步，响应包含QUEUED和生效时间；进入档案后从头复演使用相同事件时刻。

连续位置单独保存；只有真实网格节点才能构造决策请求。航段中的变化记录待重算状态，在下一节点响应；停留期间收到普通变化会在停留完成后重算。影响当前占用航段的禁入区域直接记录失败，不能穿越或跳到相邻格子。

`response_metrics` 记录收到事件至决策的仿真延迟和计算耗时；`same_state_counterfactual` 用当前真实位置、当前剩余和已完成清单，在事件前地图上重新算一次。`plan_changed` 比较动作、任务顺序及路径；`budget_changed` 另记预算变化，多个尚未响应的事件按联合影响记录，不声称逐事件因果分解。

终态：COMPLETED_RETURNED、PARTIAL_RETURNED、REFUSED、FAILED、UNAVAILABLE、CANCELLED。只有确实移动并到达基地的前两种状态才允许 `returned=true`。取消、原地拒绝和停止失败均不能计作返回；只完成任务点也不能代替返程条件。

`state` 不携带原始遥测和未来队列；`export` 包含复演所需完整执行侧配置。最新剩余Wh来自执行器，“最近决策预算”保留当时刻，页面明确标注。`result_sha256` 排除UUID、墙钟、CPU耗时等非确定字段。

服务关闭时暂停并保存，重新启动后历史记录 `runtime_available=false`，可复查和从头复演，不能进程断点恢复。复演必须匹配配置指纹、执行源码与参考曲线；不把旧档案自动升级为当前版本。

## 10/22固定条件评测扩展

`Scenario`新增配对标签`split=held_out`与`version=v2-heldout-maps-0.1`；开发地图继续使用原development/0.3组合，混用版本与标签会拒绝。业务请求合同仍为0.3，选择器和执行模型未改变。评测档案使用独立目录，不进入本机演示数据库。

源码指纹包含Scenario文件，因此10/20旧档案的严格复演须使用day20/source-snapshot中的原版本；不能跳过版本校验。新评测的完整执行源码保存在evaluation-20261022/source-snapshot。
