# 后端接口交接：前端重写时保留什么

核对日期：2026-11-13。HTTP服务为`competition-v2-api-0.3`，运行器仍为`competition-v2-runtime-0.1`，默认地址`http://127.0.0.1:8094`。当前页面只作技术验证入口；本次没有修改页面布局、默认算法、地图、能量参数或评分规则。

11 月 5 日源码审查补充了保存失败的事务回退、恢复运行时的单任务切换和后台检查点重试。11 月 13 日增加已保存终态释放和历史分页。[前一轮审查记录](BACKEND_REVIEW_20261105.md) · [当前版本与验证范围](TECHNICAL_REMAINING.md)

## 从网页跟到导出

以下路径按 2026-11-11 的本地 v2 源码核对。读程序时可以从页面的「开始巡看」一路跟到导出的 JSON。

| 操作 | 文件和函数 | 数据怎样流动 |
|---|---|---|
| 启动服务 | [launch.py](launch.py) 的 `main()` → [api.py](api.py) 的 `create_app()` | Uvicorn 启动本机 FastAPI 服务。应用启动时打开 SQLite，并创建推进仿真的后台任务 |
| 选择情景、创建运行 | [live.html](presentation/live.html) 的 `settings()`、`preview()`、`start()`、`api()` → [api.py](api.py) 的 `preview()`、`create()` | 页面送出情景、方法、温度、初始剩余 Ah 比例、预算方式和倍速。后端用 `CreateInput` 校验，调用 `preset_config()` 组装配置。预览只返回初始方案，正式创建保存运行并返回 ID |
| 计算下一步 | [runtime.py](runtime.py) 的 `RuntimeRun.__init__()`、`current_request()`、`_choose()` → [selectors.py](selectors.py) 的 `decide()` → [planning_inputs.py](planning_inputs.py) 的 `build_leg_table()`、`assess_order()` | `initial_request()` 提供参考曲线和预算，运行器传入当时已知地图、位置、电量和完成点。规划器计算有向航段、剩余顺序、返程和储备，返回动作与理由。[初始输入](scenarios.py) |
| 执行、更新页面 | [api.py](api.py) 的 `lifespan()` 内 `tick()` → [runtime.py](runtime.py) 的 `advance()` → [live.html](presentation/live.html) 的 `poll()`、`render()` | 后台按经过时间与倍速推进。运行器更新位置、耗能及遥测，停留结束才记任务完成，实际到基地才记返回。页面读取后端状态和轨迹后刷新 |
| 应用事件、重新规划 | [runtime.py](runtime.py) 的 `inject()`、`_apply_due()`、`_choose()` | 预设事件和手动事件由运行器排队，事件到时更新已知地图。符合重算条件时，`_choose()` 将更新后的当前观测传给规划器，并记录同状态比较供复查 |
| 保存、查看历史 | [api.py](api.py) 的 `persist()`、`saved_state()` → [storage.py](../core/storage.py) 的 `RunStore.save_batch()`、`get()` | 本地修订版在事务里保存快照、操作审计与可选请求编号。后台也保存运行检查点。重启后历史从 SQLite 读取，仍在内存的运行以 `runtime_available` 标识 |
| 导出、复演 | [api.py](api.py) 的 `export()`、`archive()`、`replay()` → [runtime.py](runtime.py) 的 `export()` | 导出可读取内存快照或归档，并附上操作审计。页面将响应存成 JSON。复演先校验运行器版本、执行源码、曲线和配置指纹，再按原配置从头创建一次运行 |

读导出文件时，先看 `configuration` 确认输入，再看 `decisions` 与 `events` 对齐计划和事件，最后用 `telemetry` 和 `summary` 复查执行。配置指纹对应配置内容，结果指纹覆盖摘要、遥测、事件、能耗区间和剔除决策耗时的决策记录。操作审计、运行 ID 和文件排版另有用途，核对文件原始字节时用整份文件的 SHA-256。[仿真计算读法](DESIGN.md#用一份冻结档案读计算)

## 先验证后端，再换页面

启动器启动本机FastAPI服务，算法与SQLite记录均在后端。前端可以替换为Vue或其他实现，不需要迁移任务选择器、能量计算或运行数据库。原入口继续保留，直到新前端走完同样的创建、事件、返回、导出与复演流程。

实际FastAPI生成的请求与响应合同见[http-v2.openapi.json](contracts/http-v2.openapi.json)；运行时也可访问`/openapi.json`和`/docs`。9个API操作均声明响应模型，运行时检查数据形状；状态、预算、决策、遥测、事件与审计字段有明确类型。来源说明中的扩展元数据使用JSON对象。可选字段未出现时不会补写null；能量未知值和被中断航段的覆盖判定仍保留null。完整导出指纹与运行器原始档案一致。

## 9个HTTP操作

| 方法和路径 | 输入 | 关键行为 |
|---|---|---|
| GET `/api/v2/health` | 无 | 来源、运行器版本、曲线是否可用 |
| POST `/api/v2/preview` | CreateInput | 只计算初始状态，不创建持久运行；`is_preview=true` |
| POST `/api/v2/runs` | CreateInput | 创建真实后端运行；此前RUNNING运行会暂停并保存 |
| GET `/api/v2/runs` | 无 | 历史列表；`runtime_available`区分仍在内存中的运行 |
| GET `/api/v2/history` | `limit`、`cursor` | 完整历史分页，响应为`items`和`next_cursor`，默认50条，最多100条 |
| GET `/api/v2/runs/{id}` | 路径id | 当前状态或已归档状态；建议每200ms查询，上次未结束不叠加请求 |
| POST `/api/v2/runs/{id}/control` | `{"action":"pause"}`，或resume/cancel | 控制内存中的运行；归档记录返回409 |
| POST `/api/v2/runs/{id}/events` | `{"kind":"obstacle_ahead"}`，或gust/both_gates | 排队注入事件；返回QUEUED不代表重规划已完成，要继续读取状态 |
| GET `/api/v2/runs/{id}/export` | 路径id | 完整配置、原始遥测、决策、事件、指纹和执行审计 |
| POST `/api/v2/runs/{id}/replay` | 无JSON体 | 从原配置创建新运行、新id；原档案保留。版本/源码/曲线/配置不匹配返回409 |

CreateInput示例：

```json
{"preset":"obstacle","selector_id":"value_per_cost","temperature_c":0.0,"initial_soc":0.85,"budget_mode":"bounded","speedup":20.0}
```

`selector_id`可为`fixed_order/nearest_feasible/value_per_cost/subset_dp`；预算为`nominal/bounded`。`initial_soc`是剩余容量Ah比例，不是剩余Wh比例。`low_budget`和`unavailable`预设会覆盖输入的电量或温度以构造对应边界用例。请求模型拒绝未知字段与不合规类型。HTTP422表示输入未通过模型检查，404表示没有该记录，409表示当前状态不允许操作；业务拒绝/失败也可能出现在HTTP200的状态中，不能只检查HTTP成功。

## 新前端必须保留的语义

| 字段 | 前端应怎样理解 |
|---|---|
| `position` / `executed_path` | 后端实际执行位置/轨迹，禁止按浏览器计时自行计算推进 |
| `path` / `current_decision` | 当前计划与原因，不代表已经执行完成 |
| `t_s` / `speedup` | 仿真时间/仿真倍速，不是现实飞行时间 |
| `summary.returned` | 后端实际到达基地的结果；不能用动画到终点替代 |
| `summary.remaining_wh` / `consumed_wh` / `consumed_ah` | 单位分开显示；null是信息缺失，不能补成0 |
| `summary.effective_value` | 返程且达到储备才有效；`raw_value`不能替代它 |
| `runtime_available=false` | 终态已保存并释放内存，或进程重启后成为归档；可查看/导出/从头复演，不能接着上次位置运行 |
| `pending_replan` / `queued_manual_events` | 事件或重规划尚待处理；结合后续决策记录判断响应 |

终态包含`COMPLETED_RETURNED/PARTIAL_RETURNED/REFUSED/FAILED/UNAVAILABLE/CANCELLED`，每种都要有明确文字。`PARTIAL_RETURNED`必须列出未完成任务；取消、拒绝、数据不足均不能显示为完成。

## 超时后如何安全重试

`POST /runs`和`POST /runs/{id}/replay`支持可选HTTP请求头`Idempotency-Key`。新前端为一次用户创建意图生成一次UUID，在收到明确结果前保留它；网络超时后用相同请求体和相同key重试，会取回同一个运行id及当前状态，不会再次新建或暂停其他运行。key和运行快照在同一SQLite事务保存，服务重启后仍可找回。

同一个key用于不同参数、不同原始运行或不同操作会返回409；请让新操作使用新key。key允许1—128个ASCII字母、数字、点、下划线、冒号或连字符。服务重启后找回的原运行是归档状态，不会假装断点续飞；要从头执行需另发复演操作。没有key的旧客户端保持原行为，超时后仍应先核对历史。事件和暂停等控制操作不支持该机制，不要把它推断成所有POST都可盲目重试。

本地修订版将创建或复演新记录、保存请求编号、暂停旧运行放进同一个事务，提交成功后更新内存状态。恢复一条暂停记录也会在同一事务中暂停当前运行。SQLite 读写错误返回 HTTP 503 和中文提示，创建和复演可继续使用原 key 重试。控制和手动事件的保存失败会回退该次内存变化。非法数字输入返回 JSON 格式的 HTTP 422。

## 历史分页与内存生命周期

旧`GET /api/v2/runs`仍返回最近50条的数组。完整查询使用`GET /api/v2/history?limit=50`，响应`{"items":[...],"next_cursor":"..."}`；下一页原样传回`cursor`，`next_cursor=null`表示结束。参数无效返回422，其中`detail`可能是字段校验列表或游标错误文字。

游标记录首屏的最大内部行号及最后一条记录的位置，翻页期间新建的记录不进入这一轮列表。顺序为创建时间、内部行号倒序。分页固定的是记录范围，运行中的摘要仍可更新；它不是整个数据库的冻结快照。列表仅从SQLite提取摘要和配置，不解码遥测。旧网页暂未增加翻页控件。

创建时立即拒绝、取消以及后台完成的运行，均在事务或检查点保存成功后释放内存。待重试的终态保留到提交成功；运行中与暂停中的记录仍保留，以支持继续运行。内存并非对任意数量暂停任务或持续磁盘故障都有固定上限。

强制结束进程后，以最后提交的检查点为准，未提交进展可能丢失。重启不会自动续跑。新增长期使用和故障检查工具`check_long_running`、`check_service_recovery`均要求独立输出目录；后者只终止它自己启动的本地测试进程。

示例：`Idempotency-Key: 1af13858-c845-4fba-8625-7b401b46f673`。页面断线、刷新或暂停不会删除记录；前后端优先同源部署；本机服务不是带认证的公网多用户服务。

## 不依赖页面的验收

在项目根目录运行（输出目录必须不存在）：

```bash
.competition-venv/bin/python -m competition.v2.tools.smoke_delivery --output runtime/backend-check-20261029 --verified-on 2026-10-29
```

该工具通过实际HTTP服务创建、执行、导出，检查V/I/t积分，关闭并重启服务，再读取原档案和复演。已有10/28通过记录见[evidence/delivery-service-20261028.json](evidence/delivery-service-20261028.json)。Windows换用`.competition-venv\Scripts\python.exe`；尚无Windows实机通过记录。

更完整检查使用独立包根目录的「检查Mac.command」或「检查Windows.bat」。不要修改原来的冻结实验目录；新前端测试、日常演示和正式比较分别保存数据库和输出。
