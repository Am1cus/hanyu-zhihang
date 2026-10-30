# 后端接口交接：前端重写时保留什么

核对日期：2026-10-29。HTTP服务为`competition-v2-api-0.2`，运行器仍为`competition-v2-runtime-0.1`，默认地址`http://127.0.0.1:8094`。当前页面只作技术验证入口；本次没有修改页面布局、算法、地图、能量参数或评分规则。

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
| `runtime_available=false` | 进程重启后只能查看/导出/从头复演，不能接着上次位置运行 |
| `pending_replan` / `queued_manual_events` | 事件或重规划尚待处理；结合后续决策记录判断响应 |

终态包含`COMPLETED_RETURNED/PARTIAL_RETURNED/REFUSED/FAILED/UNAVAILABLE/CANCELLED`，每种都要有明确文字。`PARTIAL_RETURNED`必须列出未完成任务；取消、拒绝、数据不足均不能显示为完成。

## 超时后如何安全重试

`POST /runs`和`POST /runs/{id}/replay`支持可选HTTP请求头`Idempotency-Key`。新前端为一次用户创建意图生成一次UUID，在收到明确结果前保留它；网络超时后用相同请求体和相同key重试，会取回同一个运行id及当前状态，不会再次新建或暂停其他运行。key和运行快照在同一SQLite事务保存，服务重启后仍可找回。

同一个key用于不同参数、不同原始运行或不同操作会返回409；请让新操作使用新key。key允许1—128个ASCII字母、数字、点、下划线、冒号或连字符。服务重启后找回的原运行是归档状态，不会假装断点续飞；要从头执行需另发复演操作。没有key的旧客户端保持原行为，超时后仍应先核对历史。事件和暂停等控制操作不支持该机制，不要把它推断成所有POST都可盲目重试。

示例：`Idempotency-Key: 1af13858-c845-4fba-8625-7b401b46f673`。页面断线、刷新或暂停不会删除记录；前后端优先同源部署；本机服务不是带认证的公网多用户服务。

## 不依赖页面的验收

在项目根目录运行（输出目录必须不存在）：

```bash
.competition-venv/bin/python -m competition.v2.tools.smoke_delivery --output runtime/backend-check-20261029 --verified-on 2026-10-29
```

该工具通过实际HTTP服务创建、执行、导出，检查V/I/t积分，关闭并重启服务，再读取原档案和复演。已有10/28通过记录见[evidence/delivery-service-20261028.json](evidence/delivery-service-20261028.json)。Windows换用`.competition-venv\Scripts\python.exe`；尚无Windows实机通过记录。

更完整检查使用独立包根目录的「检查Mac.command」或「检查Windows.bat」。不要修改原来的冻结实验目录；新前端测试、日常演示和正式比较分别保存数据库和输出。
