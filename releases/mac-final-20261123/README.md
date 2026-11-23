# Mac 电脑端终版 · 2026-11-23

[发布页与下载附件](https://github.com/Am1cus/hanyu-zhihang/releases/tag/mac-final-20261123) · [ZIP 的 SHA-256](SHA256SUMS.txt) · [使用说明](../../competition/v2/MAC_FINAL.md)

| 要找什么 | 入口 |
|---|---|
| 冰川蓝工作台、巡看仿真与运行记录 | [服务源码](../../competition/v2/) |
| 三输入续航和能耗 A* 1.1 | [模型、算法与接口](../../competition/endurance/) |
| LSTM 推理程序、三个冻结权重和示例输入 | [模型发布目录](../../Phase4/releases/energy_residual_lstm_v3_rc1/) |
| −20 ℃、80% 电量、5 m/s 的预测与路线 | [剩余分钟](results/续航.json) · [预计折返点](results/默认往返.json) |
| 强风路线与途中返航 | [两种路线对照](results/强风往返.json) · [重规划](results/中途重规划.json) |
| LSTM 对随后 10 秒耗电量的预测 | [运行输出](results/lstm.json) |
| 版本复查 | [Mac 验包记录](results/Mac验包.json) · [A* 1.0 与 1.1 同条件比较](results/A星版本对照.json) |

上述运行结果来自本机软件与仿真。地图、温度和电池条件随各份运行输出或示例输入保存。
