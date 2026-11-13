# 独立研究：已完成区间功率候选

研究代码与默认v2软件分开。候选`completed-interval-power-20261113-0.1`不会由网页选择，也不进入普通离线运行包。它沿用原模型与预算，只在已有决策时刻使用此前已完成区间更新功率估计。

[本轮结果与边界](../v2/TECHNICAL_NEXT_20261113.md) · [全部确认结果](../v2/evidence/candidate-confirmation-20261113.csv)

从仓库根目录使用固定比赛环境。以下是新目录复现示例，不能指向已存在的正式证据目录：

```bash
.competition-venv/bin/python -m unittest discover -s competition/research_v2/tests -v
.competition-venv/bin/python -m competition.research_v2.check_correctness --output ../output/4C/v2/my-correctness
.competition-venv/bin/python -m competition.research_v2.experiment freeze --phase development --output ../output/4C/v2/my-development --correctness ../output/4C/v2/my-correctness/report.json
.competition-venv/bin/python -m competition.research_v2.experiment run --output ../output/4C/v2/my-development
.competition-venv/bin/python -m competition.research_v2.experiment freeze --phase confirmation --output ../output/4C/v2/my-confirmation --correctness ../output/4C/v2/my-correctness/report.json --development ../output/4C/v2/my-development/report.json
.competition-venv/bin/python -m competition.research_v2.experiment run --output ../output/4C/v2/my-confirmation
```

这套种子现已使用，再执行只是复现。新的研究确认需要另行制定并冻结新条件。代码在冻结前记录候选与执行源码哈希，再生成地图；运行时验证哈希、配置和配对。每个案例保存压缩原档、独立结果及日志；运行不自动补跑，超时/失败留在分母中。

候选档案的`configuration`包含`experiment_version`与`base_configuration`，必须用`CandidateConfig`和`CandidateRun`复演。普通`RuntimeConfig`及HTTP复演会拒绝它。运行前锁定的源码快照保存在本地批次目录；隔离快照的导入辅助文件补充记录见`snapshot-support.json`。

算法没有读取未来事件或未来耗电，也没有直接使用真实剩余能量纠正原观测。尚未完成的区间不参与功率更新，初始观测和已有偏差保留。因此本策略仍可能出现储备不足，不能作为实飞安全保证。
