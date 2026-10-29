# 后端接口交接：前端重写时保留什么

核对日期：2026-10-29。当前运行器为`competition-v2-runtime-0.1`，默认地址`http://127.0.0.1:8094`。当前页面只作技术验证入口；本次没有修改页面布局、算法、地图、能量参数或评分规则。

## 先验证后端，再换页面

启动器启动本机FastAPI服务，算法与SQLite记录均在后端。前端可以替换为Vue或其他实现，不需要迁移任务选择器、能量计算或运行数据库。原入口继续保留，直到新前端走完同样的创建、事件、返回、导出与复演流程。

实际FastAPI生成的请求合同见[http-v2.openapi.json](contracts/http-v2.openapi.json)；运行时也可访问`/openapi.json`和`/docs`。**当前响应未全部声明为Pydantic模型，因此OpenAPI不能完整生成响应类型。** 响应字段以下表、`runtime.py`的`state()/summary()/export()`及`api.py`为准；后续若补齐响应模型，应单独检查兼容性，不能称本快照已经覆盖全部响应字段。

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

创建接口目前没有客户端幂等键。创建请求超时后先查询历史并核对，不能盲目自动重发。页面断线、刷新或暂停不会删除记录；丢失回执不等于后台操作没有发生。前后端优先同源部署；本机服务不是带认证的公网多用户服务。

## 不依赖页面的验收

在项目根目录运行（输出目录必须不存在）：

```bash
.competition-venv/bin/python -m competition.v2.tools.smoke_delivery --output runtime/backend-check-20261029 --verified-on 2026-10-29
```

该工具通过实际HTTP服务创建、执行、导出，检查V/I/t积分，关闭并重启服务，再读取原档案和复演。已有10/28通过记录见[evidence/delivery-service-20261028.json](evidence/delivery-service-20261028.json)。Windows换用`.competition-venv\Scripts\python.exe`；尚无Windows实机通过记录。

更完整检查使用独立包根目录的「检查Mac.command」或「检查Windows.bat」。不要修改原来的冻结实验目录；新前端测试、日常演示和正式比较分别保存数据库和输出。
