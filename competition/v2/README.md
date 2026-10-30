# 寒域智航 v2：任务取舍与返程决策

**10月30日后台收尾：** 9个API响应合同、跨重启创建/复演去重、严格验包及UTF-8启动已完成。102项v2检查和31项旧版回归通过；目标电脑实测仍待完成。页面未改。

**10月29日：** 暂停界面优化，当前页面作为技术验证入口；前端重写参考[后端接口交接](BACKEND_HANDOFF.md)。已有实验数字与适用边界见[技术证据核验](EVIDENCE_REVIEW_20261029.md)。

**10月28日：** 独立离线包、全新Mac环境验证、同版90秒备用视频已完成，见[技术交付记录](DAY28_DELIVERY.md)。Windows实机及目标电脑投影播放仍待验收。

**现在试用：双击项目根目录的「启动寒域智航.command」，浏览器会自动打开。** 已完成本机三轮场景操作、刷新恢复、断连重试、服务重启和复演核验。五步操作见[试用说明](TRY_IT.md)，本轮修复与证据见[可用版本记录](DAY27_USABLE.md)。

状态（2026-10-23收尾）：本机参考仿真与动态调整已接通；10月22日已完成4张新测试地图上的1,152项固定条件执行，73项软件检查通过，抽取24项复演一致。实验结果、通俗讲法及未完成事项见[本轮交付记录](DAY22.md)。真人试用、正式PPT更新仍待完成；储备比例敏感性已于10/27补齐；访谈暂缓，真实飞行验证为0。

2026-10-22：根据硬件限制，本轮不安排线下采集与真机测试；采用[纯软件验证方案](VALIDATION_SOFTWARE.md)，真实飞行性能保持未经验证。

2026-10-27：已完成10%/20%/30%储备补充比较，共3,456项执行（含1,152项原设置对照），82项软件检查通过。见[本轮结果与技术余项](DAY27.md)；最新交付状态见[技术清单](TECHNICAL_REMAINING.md)。

核心问题：**天气变差、电量有限时，先完成哪些重要巡检点，放弃哪些，为什么？**

- [当前任务规格0.3：需求映射、接口与开发场景](TASK_SPEC_0_3.md)
- [黑龙江应用定位、点位名称与讲解方式](APPLICATION_HLJ.md)——辅助巡看为主，导览与轻物资配送作为扩展。
- [1,152项实验结果、讲法与边界](DAY22.md)
- [日期计划、负责人及验收](PLAN.md)
- [任务规格与实验方案](DESIGN.md)
- [D2接口、地图与记录合同](INTERFACE.md)
- [学生需求核对表](NEEDS_CHECK.md)
- [机器可读实验设计](protocol.json)
- [五点手算输入](fixtures/day1_example.json)

日期计划是 v2 后续工作的安排依据；旧版 `STUDENT_TASKS.md` 保留历史，不再作为新阶段日期表。11 月 29 日为团队内部封版目标，正式报名及下一届赛事要求须另核对。

## 当前运行演示入口

Mac可双击 [start_v2.command](start_v2.command)，或根目录「启动寒域智航.command」；会检查依赖并打开 <http://127.0.0.1:8094/>。命令行入口：在`learn`目录执行 `.competition-venv/bin/python competition/v2/launch.py`。首次安装需要联网，之后可离线演示；当前操作说明见[TRY_IT.md](TRY_IT.md)。Windows入口[start_v2.bat](start_v2.bat)已编写，实机核验待完成。10/20历史说明保留在[DAY20.md](DAY20.md)。

页面按“先安排、途中调整、回来复查”组织，可切换投影用的讲解模式。运行档案使用v2独立数据库。网页上的移动位置来自后端执行状态。

开发验收：

```bash
.competition-venv/bin/python -m competition.v2.tools.prepare_day20 --output ../output/4C/v2/day20 --verified-on 2026-10-20
```

以后复核请填写实际日期并使用新的输出目录；保留已交付证据。

## 10月13日历史算法与方案对照入口

在 `learn` 目录使用原比赛虚拟环境：

```bash
.competition-venv/bin/python -m competition.v2.tools.prepare_day13 --output ../output/4C/v2/day13 --verified-on 2026-10-20
```

生成 `方案对照.html`，可直接用浏览器打开；切换展示已计算的条件，支持导出本例。全部38个条件与152条决策保存在同目录JSON中，属于开发快照，不是正式飞行执行。以后复核填写实际日期并改用新的输出目录。讲解见[PRESENTATION_STORY.md](PRESENTATION_STORY.md)。

## D1历史教学入口

在 `learn` 目录执行，Python 标准库即可，不安装依赖、不启动旧服务：

```bash
python3 competition/v2/tools/check_day1_contract.py --output ../output/4C/v2/day1-contract-check.json
```

它枚举五个点的全部 326 个有序子集，核对手算预算、方向不同的返程代价、缺数据、不可达、误差边界与三种简单策略。程序是参考计算器，尚未接入网页或飞行执行器。输入中的 Wh 是人为设置的教学数值，不能当作真实无人机或 P42A 测量。

当前可复核的输出、当天完成记录及 v1 文件指纹位于工作区 `output/4C/v2/`。正式 v2 实验另建目录，绝不把这个教学例计入正式样本。

## 10月11日需求、接口与开发场景检查

```bash
.competition-venv/bin/python -m competition.v2.tools.prepare_day11 --output ../output/4C/v2/day11 --verified-on 2026-10-13
```

本次为10月11日工作项，最终复核日期为2026-10-13；以后重跑应填写实际复核日期。10月11日首轮结果已保存在`output/4C/v2/day11/checkpoint-20261011/`。


使用现有 Python 3.12 / Pydantic 2.13.5 环境。该命令导出Schema、样例请求、有向航段、预算和开发检查，并核对决策记录与请求。它不启动网站、不创建飞行运行、不写原版数据库。两份需求记录位于工作区output/4C/v2/needs，为公开资料核对。0.2源码保存在output/4C/v2/day11/before/source；day2输出保持历史记录，旧入口已阻止以0.3覆盖它。
