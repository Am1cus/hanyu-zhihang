# 10月28日：本机技术交付收尾

当前源码、启动器、离线依赖、检查工具和90秒实际运行录屏已组成独立交付版。GitHub首页和仓库简介已更新，原LSTM/AirSim研究支线保留。

## 已经交付

| 项目 | 本轮实际证据 |
|---|---|
| 独立程序包 | 不依赖旧Java、AirSim或LSTM；包内运行记录单独保存在`runtime/` |
| 离线首次安装 | 在带中文和空格的新目录、全新虚拟环境中启动；强制`PIP_NO_INDEX=1`，使用包内固定依赖完成安装 |
| 回归检查 | 独立包87项软件检查及`pip check`通过，文件指纹无差异 |
| 真正启动服务 | 通过HTTP创建执行、实际返回、导出、关闭服务、重新启动和复演；复演结果一致 |
| 当前版本备用视频 | 90.00秒，1920×1080、H.264、无音轨；实际录屏，20倍仿真，未改轨迹或结果；录屏对应档案可重新执行得到相同结果 |
| 版本一致性 | 软件、参数、界面、视频及对应档案有SHA-256记录；原1,152项和3,456项冻结证据保持不变 |
| 组员验机工具 | 包内「检查Mac.command」「检查Windows.bat」，一键检查文件、依赖、软件、服务重启与复演 |

机器报告见[本轮技术交付记录](evidence/technical-delivery-20261028.json)、[独立包检查](evidence/delivery-verification-20261028.json)、[服务检查](evidence/delivery-service-20261028.json)、[离线安装](evidence/offline-install-20261028.json)和[视频来源](evidence/video-manifest-20261028.json)。

## 仍需在比赛电脑上做的一件事

**组员拿包后，用实际比赛电脑启动一次，再双击对应检查脚本，最后试播视频。** 软件检查约一分钟，真实操作和播放建议再留五分钟。报告在`runtime/checks-日期时间/verification.json`。

本轮验证平台是Apple芯片Mac、Python3.12。Windows x86-64离线依赖与脚本已提供，但没有Windows实机结果。GitHub连接不具备工作流写入权限，未能建立Windows自动检查；没有把“准备了Windows文件”记成“Windows通过”。实际投影和PowerPoint/WPS播放也需要目标电脑核对。

因此，本机软件工程交付已经收尾；跨电脑最终验收仍保留为明确余项。正式PPT、真人答辩计时及报名材料单独推进，不算在本轮技术交付里。

## 使用入口

源码仓库：[Am1cus/hanyu-zhihang](https://github.com/Am1cus/hanyu-zhihang)。

交付包说明见[PORTABLE_README.md](PORTABLE_README.md)。下载完整ZIP后解压，不要只复制启动文件。Python3.12需预先安装；包内离线依赖覆盖Apple芯片Mac和Windows x86-64，不能直接用于Intel Mac或Windows ARM。

视频是备用演示素材，不是真人正式答辩录像。若后续改动执行代码、参考参数或界面，需要重新核验和录制，不能继续把旧视频标成新版本。
