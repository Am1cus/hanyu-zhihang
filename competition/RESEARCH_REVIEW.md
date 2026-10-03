# 《寒域智航》证据与评委表达：快速研究简报

**检索与审查日期：2026-10-03。模式：academic-research-suite / deep-research quick。**

**研究问题：**在两人、总预算 1 万元、10 分钟答辩的 4C 算法作品约束下，如何改进现有《寒域智航》的证据和表达，使非无人机评委理解决策价值？赛道采用已经确认的“软件应用与开发—算法设计与应用”。

**AI 披露：**本简报为 AI 辅助形成性分析，与软件开发共享助手、项目上下文及本地证据，不构成独立专家评审。公开来源已核查原始发布页面或论文文本，本地结果由冻结档案与源码核对。它不是评委认证、获奖预测或真实飞行认证。建议已用于改进讲稿与材料表达，冻结算法、场景和评测结果保持原版本。

## 结论与适用范围

**我的推断：**作品最清楚的主线是“能做多少、何时返航、凭什么这样判断”。用巡检、返程、储备三笔能量账，串起预演、事件、在线决策和复算档案。现有证据支持一个可运行、可解释、可复演的任务决策软件；尚不支持真实无人机节能、安全保证或原创飞行动力学模型。

**已证据支持：**2026 年官方规则允许经典算法，算法小类强调用编程解决实际问题；队伍可由 2～9 名本科生组成，陈述含演示不超过 10 分钟。两人方案符合这一规模规定。此处依据已公布的 **2026 年**规则，后续参赛年度仍需核对新规。[中国大学生计算机设计大赛组委会（2026）](https://jsjds.blcu.edu.cn/gsjs1/jnjsq.htm)<!--ref:4c2026--><!--anchor:section:说明（5）（8）（9）-->

**建议：**保留本机二维、固定高度、单机、固定任务顺序的范围；把硬件预算与开发时间用于后续校准准备。答辩先展示一次具体取舍，再解释算法和来源。现阶段增加三维动画或强行接入 LSTM，不会自动增加证据强度。

## 已证据支持、推断与建议

### 1. 场景有政策关联，用户需求仍需独立验证

**已证据支持：**国办发〔2024〕49 号把辽宁、吉林、黑龙江等纳入北方冰雪经济引领区，并提出冰雪旅游优化、相关企业数字化转型及安全管理要求。它支持“东北冰雪景区”作为应用背景。[国务院办公厅（2024），国家体育总局官方发布](https://www.sport.gov.cn/dyzx/n5168/c28254727/content.html)<!--ref:icepolicy2024--><!--anchor:section:三（五）（八）、五（十二）、九（二十三）-->

**我的推断：**景区巡检是与该背景相容的应用设想。政策文本没有验证本作品的客户需求、采购意愿或算法效果。

**建议：**PPT 用一句背景加原文链接，随即展示“剩余能量是否够完成三个点并返程”。后续安排景区工作人员或巡检操作者访谈，访谈完成之前使用“面向景区巡检的设想”，不写“已落地景区”。

### 2. 低温依据可追溯，模型条件需要同时展示

**已证据支持：**Molicel P42A v1.7 的温度放电图对应 23℃ 充电、4.2 A 恒流放电、2.5 V 截止等条件。[Molicel（无日期，v1.7）](https://www.molicel.com/cn/wp-content/uploads/INR21700P42A_1.7_Product-Data-Sheet-of-INR-21700-P42A-80092.pdf)<!--ref:molicelp42a17--><!--anchor:section:Discharge Temperature Characteristics-->

冻结实现把厂家曲线数字化，用理想 4S1P 虚拟组积分；23℃ 参考能量为 60.32 Wh，−20℃ 为 52.08 Wh，下降约 13.66%。−10℃ 的 54.51 Wh 是插值结果，不能称为厂家该温度的实测值。[本地正式报告：curve_status](/Users/kedong/Documents/大创项目/LSTM/output/4C/evidence/formal/report.json)

**我的推断：**这些数据足以说明本参考模型的温度输入改变可用能量。它们没有识别真实无人机的推进功率、热变化、内阻、载荷或电池包管理行为；能量减少 13.66% 也不能直接换成真实续航减少 13.66%。

**建议：**温度图旁保留“厂家单节参考曲线 → 理想虚拟组 → 软件任务仿真”三步，标出恒流条件与插值节点。避免把制造商测试画面当作团队低温实验。

### 3. 1.59% 是有条件的结果，当前规划目标等价于最短时间

**已证据支持：**A* 是已有的最小代价路径方法，原论文讨论图上的代价搜索；使用它符合经典算法应用的作品定位。[Hart、Nilsson 与 Raphael（1968）](https://doi.org/10.1109/TSSC.1968.300136)<!--ref:hart1968--><!--anchor:section:I. Introduction、I.B. Some Definitions About Graphs-->

本实现采用相同预测器、任务、储备和返航规则，只替换距离或能量路线目标。每条边的估算为：

`估算能量 = 固定上界功率 × 通过该边的时间 / 3600`

其中上界功率为 `4.2 V × 4 节 × 4.2 A = 70.56 W`。固定正功率乘以总时间，意味着每次“能量 A*”规划与该风场下的最短时间规划具有相同目标。执行器虽然另外积分厂家 V(Q) 曲线，但其恒流放电量仍由时间推进：相同温度、初始状态及电流下，耗能随累计时间增加。[规划源码](/Users/kedong/Documents/大创项目/LSTM/learn/competition/core/planning.py)、[执行源码](/Users/kedong/Documents/大创项目/LSTM/learn/competition/core/simulator.py)

正式 24 个配对场景的平均参考模型耗能差为 **1.593%**。这是同等完成工作量、均返航的 24 对结果均值，不是总体真实飞行节能率，也没有统计证据说明它可推广到其他地图或飞机。[本地正式报告：pairs、aggregate](/Users/kedong/Documents/大创项目/LSTM/output/4C/evidence/formal/report.json)

**我的推断：**1.59% 可以来自风影响地速后选择更快路线，不能证明独立的功率优化、原创 UAV 能耗模型或温度感知路径创新。厂家曲线积分避免“直接用规划代价当作执行测量”，但仍属于参考模型执行，不能取代物理测量。

**建议：**答辩如实称为“风场下的时间与参考能量代价规划”。把 1.59% 放在对照页或附录，注明模型条件。贡献重点放在任务预算、实时取舍、解释记录与复算闭环。后续若研究非恒定功率，需另外定义并校准负载模型，同时加入时间最短基线，再检验是否存在超出时间最短化的收益。

### 4. “全部完成”与“返回起点”必须分开，储备参数没有最优证明

**已证据支持：**正式批次为 24 个软件场景、两种策略共 48 次执行：44 次完成全部三点，4 次完成部分巡检后返回，48 次返回起点，真实飞行次数为 0。两种策略使用相同预算 guard，两者返回率都为 100%。[本地正式报告：aggregate](/Users/kedong/Documents/大创项目/LSTM/output/4C/evidence/formal/report.json)

**我的推断：**这些结果证明已冻结场景中的软件行为可执行，不能证明能量路线策略提高了返航成功率，也不能证明 guard 相对无 guard 的因果收益；该消融对照尚未开展。

储备比例 10% / 20% / 30% 的敏感性批次，全部任务完成次数分别为 **48 / 44 / 36**，三组都返回 48 次。负载估算偏差 ±10% 和风观测偏差 ±0.5 m/s 另有独立批次。它们复用同一组 24 个场景，不是新的现场样本；“负载偏差”保持执行器 4.2 A，改变估算电流，不能称为变负载电池实测。[10% 储备报告](/Users/kedong/Documents/大创项目/LSTM/output/4C/evidence/sensitivity/reserve-0.10/report.json)、[20% 储备报告](/Users/kedong/Documents/大创项目/LSTM/output/4C/evidence/sensitivity/reserve-0.20/report.json)、[30% 储备报告](/Users/kedong/Documents/大创项目/LSTM/output/4C/evidence/sensitivity/reserve-0.30/report.json)、[负载偏差 +10%](/Users/kedong/Documents/大创项目/LSTM/output/4C/evidence/sensitivity/load-+0.10/report.json)、[风偏差 +0.5 m/s](/Users/kedong/Documents/大创项目/LSTM/output/4C/evidence/sensitivity/wind-+0.50/report.json)

**建议：**用这组结果说明储备与任务量的取舍，避免“20% 最优”“10% 会坠机”。储备当前是 23℃ 参考能量的比例；在线预算只面向下一点，整任务预算面向所有剩余点，二者都依据当前已观测风场，不能表述为未来天气保证。

NASA 的相关研究用剩余飞行时间与 SOC 阈值告警，并通过真实飞行和故障扰动检验预测性能。这说明真实验证与不确定性测试的重要性，不能把其阈值或验证结论移植给本软件。[Kulkarni、Hogge 与 Quach（2018）](https://ntrs.nasa.gov/citations/20180004466)<!--ref:nasa2018--><!--anchor:section:Abstract-->

### 5. 展示一个具体取舍，优先说明因果链

**已证据支持：**`low_budget-s1-t-20-energy` 初始整任务预算为：可用 **27.19 Wh**，三点巡检 **13.27 Wh**，最终返程 **4.35 Wh**，储备 **12.06 Wh**，总需求 **29.68 Wh**；当前模型给出的可完成前缀为 1 点。完成第一点后，下一点预算差为 −0.00743 Wh，已非常接近边界。[冻结个案档案：state.initial_whole_mission_budget、decisions](/Users/kedong/Documents/大创项目/LSTM/output/4C/evidence/formal/runs/low_budget-s1-t-20-energy.json)

**我的推断：**初始“27.19 对 29.68”更适合解释完整任务不足；7.43 mWh 的差值不适合包装成物理上精确的危险边界，因为曲线数字化和真实负载误差尚未量化到这个精度。

**建议：**现场先展示整任务预演，再展示逐点重算与返航记录。对动态事件，标注“到下一地图节点后重决策”：现有批次节点决策计算耗时 **P99 约 2.45 ms**，事件到新决策的模拟延迟为 **8 s**，两者不是同一指标；20 倍播放速度也不是响应性能。[本地正式报告：response_timings](/Users/kedong/Documents/大创项目/LSTM/output/4C/evidence/formal/report.json)

**已证据支持：**Garner 与 Alley 对 110 名工程本科生的受控展示研究中，“句子结论标题 + 视觉证据”的材料组在理解与误解指标上优于常见标题加要点材料组。[Garner 与 Alley（2013）](https://www.ijee.ie/articles/Vol29-6/23_ijee2791ns.pdf)<!--ref:garner2013--><!--anchor:section:2.1 Participants、3. Results、5. Conclusions-->

**我的推断：**这一方法值得用于跨专业答辩，但该研究不是 4C 评委实验，不能保证获奖。应用后仍需让不熟悉无人机的同学复述作品的决策。

## 最该准备的三个评委追问

| 追问 | 可用的诚实回答 | 目前证据边界 |
|---|---|---|
| 没有真机，低温效果怎么验证？ | 曲线来自厂家原始条件，软件积分与决策可复算；−10℃ 明确标插值。展示来源、条件和一次原始档案。 | 真实飞机、真实景区、实测低温电池均尚未验证。 |
| A* 已经存在，1.59% 的创新是什么？ | 当前固定功率代价等价于最短时间，贡献是把已有算法与逐点任务预算、返程储备和解释档案做成可运行应用。 | 不宣称原创能耗模型；广泛节能与算法新颖性没有成立。 |
| 为什么留 20%，接近阈值时可信吗？ | 它是显式工程参数；10/20/30% 批次呈现任务量变化。展示估算偏差敏感性，承认阈值附近的模型不确定性。 | 未证明 20% 最优或真实安全；未完成误差区间、风险概率与物理校准。 |

## 30 秒通俗讲法（建议稿）

> 冰雪景区巡检，要把下一项任务和返程一起算清楚。寒域智航把能量分成巡检、返程和储备三笔账。风或障碍改变后，系统重新计算，解释继续还是返航，并保存路线和耗能供复算。当前是有厂家曲线依据的软件仿真，48 次对照中有 4 次减少巡检点后返回，后续再做设备验证。

## 可立即应用的 PPT 优化（不改冻结结果）

| 位置 | 建议结论标题与画面 | 演讲目的 |
|---|---|---|
| 开场 | “接下一项任务前，先把回程所需能量留出来”；三点地图与一项选择 | 30 秒内交代谁在做什么决定。 |
| 背景 | 一句东北冰雪场景与政策依据，角落放原文链接 | 避免长政策段落挤占演示。 |
| 方法 | “每个点都算巡检、返程、储备三笔账”；三个 Wh 区块加比较符号 | 先解释用户能理解的规则，再给 A* 名称。 |
| 来源 | 厂家图、虚拟组、软件仿真三步；注明 4.2 A 与 −10℃ 插值 | 让评委区分数据依据与团队验证。 |
| 预演 | 27.19 Wh 对 29.68 Wh，显示预计完成 1 点 | 把整任务不足与下一点可做并列说明。 |
| 现场 | 事件 → 下一节点 → 决策理由 → 返回 → 导出；对应真实日志时间 | 证明软件闭环，注明模拟时间与播放倍率。 |
| 结果 | 48 次执行中：44 全部完成、4 部分完成、48 返回；旁列储备取舍 | 分开展示任务量和返回，附“24 个软件场景、0 次实飞”。 |
| 附录 | 1.59% 配对结果与固定负载条件；计算耗时和模拟延迟分开 | 准备技术追问，避免小收益承担整个作品主张。 |

**建议验收表达：**让两名不熟悉无人机的同学听一遍，分别回答“为什么会返航”“48 次返回是否等于全部任务完成”“厂家数据和团队实测有何区别”。记录原话再修改讲稿；未做这个小测试之前，不写“已证明评委易懂”。两名队员分别负责规则与证据讲解、现场操作与档案复算，把正式内容排练到约 9 分钟，给现场操作留出余量。这是排练建议，不是本次已开展的用户研究。

## 研究记录、来源核验与局限

本次为目的性快速检索，使用公开题名和通用检索词：`site:jsjds.blcu.edu.cn 2026 算法设计与应用`、`冰雪运动高质量发展 冰雪经济 国务院`、`Molicel P42A 1.7`、`Hart Nilsson Raphael 1968 minimum cost paths`、`site:ntrs.nasa.gov remaining flying time battery prognostics`、`Garner Alley 2013 assertion evidence comprehension`。优先纳入官方规则、政府发布、厂家数据及原始研究，排除可替代的转载与营销叙述；没有向外部检索服务发送私有源码或档案。

已核验 6 个一手来源的发布主体、题名和支持内容；Hart 论文另核对 DOI 解析与原文。另外尝试了 Semantic Scholar 公开元数据辅助查询，但因 HTTP 429 或连接关闭均为 **[S2-API-UNAVAILABLE]**，没有获得可用验证结果。本简报的依据为原发布页、原文与公开检索，不声称完成程序化文献验证。未完成系统综述、全面撤稿/利益冲突审计或用户实验，也不套用临床证据等级评价法规与数学论文。

| 来源与书目信息 | 原始定位及适用证据 | 核验与限制 |
|---|---|---|
| 中国大学生计算机设计大赛组委会（2026）。软件应用与开发（2026-03-01 更新）。 | [官方类别规则](https://jsjds.blcu.edu.cn/gsjs1/jnjsq.htm)<!--ref:4c2026--><!--anchor:section:说明（5）（8）（9）-->，说明（5）（8）（9）。 | 官方一手规则；只证明该年度规则，不预测下一年度。 |
| 国务院办公厅（2024-10-31）。关于以冰雪运动高质量发展激发冰雪经济活力的若干意见，国办发〔2024〕49 号。 | [国家体育总局官方发布](https://www.sport.gov.cn/dyzx/n5168/c28254727/content.html)<!--ref:icepolicy2024--><!--anchor:section:三（五）（八）、五（十二）、九（二十三）-->，三（五）（八）、五（十二）、九（二十三）。 | 官方政策一手文本，转载页注明有删减；引用条款可见。不证明本作品需求或效果。 |
| Molicel（版本 1.7，PDF 未明确出版年）。INR-21700-P42A Product Data Sheet。 | [厂家原 PDF](https://www.molicel.com/cn/wp-content/uploads/INR21700P42A_1.7_Product-Data-Sheet-of-INR-21700-P42A-80092.pdf)<!--ref:molicelp42a17--><!--anchor:section:Discharge Temperature Characteristics-->，Discharge Temperature Characteristics。 | 商业厂家的参考数据，有条件且非性能保证；本地数字化来源可追溯。 |
| Hart, P. E., Nilsson, N. J., & Raphael, B.（1968）。A formal basis for the heuristic determination of minimum cost paths. *IEEE Transactions on Systems Science and Cybernetics, 4*(2), 100–107。 | [DOI](https://doi.org/10.1109/TSSC.1968.300136)<!--ref:hart1968--><!--anchor:section:I. Introduction-->；[高校保存的原论文](https://people.stfx.ca/jdelamer/courses/csci-564/_downloads/b2220c66675ddde471ca1795147b8e86/A_Formal_Basis_for_the_Heuristic_Determination_of_Minimum_Cost_Paths.pdf)<!--ref:hart1968--><!--anchor:section:I.B. Some Definitions About Graphs-->，I、I.B。 | 原始算法论文；解释已有方法，不证明本应用的新颖性或外部有效性。 |
| Kulkarni, C., Hogge, E., & Quach, C. C.（2018-07-09）。Remaining flying time prediction implementing battery prognostics framework for electric UAV’s. AIAA Propulsion and Energy；NASA 文档 20180004466。 | [NASA 原始记录及摘要](https://ntrs.nasa.gov/citations/20180004466)<!--ref:nasa2018--><!--anchor:section:Abstract-->。 | 原始研究机构文献，摘要明确实飞与故障测试；本简报未声称审查其全部实验。 |
| Garner, J. K., & Alley, M. P.（2013）。How the design of presentation slides affects audience comprehension: A case for the assertion–evidence approach. *International Journal of Engineering Education, 29*(6), 1564–1579。 | [期刊原论文](https://www.ijee.ie/articles/Vol29-6/23_ijee2791ns.pdf)<!--ref:garner2013--><!--anchor:section:2.1 Participants、3. Results、5. Conclusions-->，§2.1、§3、§5。 | 110 名本科生受控研究；作者也是该展示方法研究者，向竞赛答辩迁移需本地检验。 |

**整体证据边界：**同一电芯、恒流参考条件、合成地图和有限参数扰动，支持复现性与软件行为验证。没有真实巡检测量、实际用户效用、物理安全概率或广泛节能效果的证据。建议优先改进讲法、指标标签与问答，其次开展独立校准和用户研究；未来新增实验应另存版本，保留本次冻结结果。
