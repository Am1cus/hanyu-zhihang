# 寒域智航：拿到包后怎么用

当前源码接口0.4，包含新增续航预测和省电路径入口。实际运行包版本、源提交和文件指纹以 `PACKAGE_MANIFEST.json` 为准；历史 `v2-backend-20261113` 包使用接口0.3，不包含新增功能。

这是本机二维参考仿真，不控制真实无人机。

1. **先完整解压ZIP。** 不要在压缩文件预览里直接运行，也不要只复制一个启动文件。
2. **准备Python 3.12。** Windows安装时带上Python Launcher；Mac需能在终端使用`python3.12`。Python本身不在本包内。
3. Mac双击根目录「启动寒域智航.command」；Windows双击「启动Windows.bat」。首次会创建`.competition-venv`。带`wheelhouse`目录的包直接使用内置依赖，不需要联网。
4. 浏览器打开本机的「续航与路线」首页。保持启动窗口开着，填入天气和电量后点「计算续航」。可从顶部进入「巡看仿真」或「运行记录」。[本机首页](http://127.0.0.1:8094/)
5. 停止服务时在启动窗口按Control+C。记录在本包`runtime/missions-v2.sqlite3`，下次仍可查看；服务重启后只能从头复演。

「更多条件」可改电池容量、平飞地速和储备比例。续航使用已随包提供的 AirSim 参考机型，巡看仿真使用 P42A 电芯参考曲线。操作说明见包内的 `competition/endurance/README.md`。

内置依赖适用于**Python 3.12、Apple芯片Mac及64位Windows（x86-64）**。Intel Mac、Windows ARM或其他Python版本不能直接使用这套离线依赖；不要把下载了Windows依赖等同于Windows已经完成实机验证。

初次解压到另一台电脑时不要携带旧`.competition-venv`；它是机器相关环境。保留原包备份，在新目录中首次启动即可重新创建。日常记录可通过页面导出JSON；保存整个`runtime`目录前应先停止服务。

## 简单演示顺序

进入「巡看仿真」，读起飞预览后开始。可在「改变环境」加入禁入区，查看调整原因和返程。在「运行记录」打开对应条目并导出。默认按 20 倍推进仿真，可暂停后继续。

连接中断时，画面是最后收到的状态，后台可能仍在运行；页面会重连，不会自动重发刚才的操作。遇到电量不足、超出温度范围或极端强风，会明确显示拒绝、信息不足或失败。

已结束记录在保存成功后自动释放内存。「运行记录」先显示最新 50 条，点击「显示更早记录」继续翻页。任一记录可查看详情、导出或从头复演。

## 文件位置

- `competition/v2/`：程序、模型合同、测试和说明。
- `competition/endurance/`：直接续航预测模型、优化 A* 和页面。
- `competition/data/p42a_reference.json`：带来源的低温参考参数。
- `competition/v2/evidence/`：公开实验摘要与全部逐项统计，完整遥测档案另行保存。
- `PACKAGE_MANIFEST.json`：包内文件指纹，用来核对代码、参数、说明和视频。
- `media/`：若已随包提供，为当前版本实际运行录屏及对应运行记录，不能当真人答辩视频。

在根目录可运行：`.competition-venv/bin/python -m unittest discover -s competition/v2/tests -v`；Windows将Python路径换为`.competition-venv\Scripts\python.exe`。

组员在实际比赛电脑上可双击「检查Mac.command」或「检查Windows.bat」。约一分钟完成文件指纹、依赖、软件检查、服务重启与复演，报告保存在`runtime/checks-日期时间/verification.json`。它仍不能代替实际点击、投影和PowerPoint/WPS播放检查。

新版检查器在清单丢失、损坏或文件指纹不符时停止，不会继续运行包内代码并显示通过；请从完整原包重新解压。检查脚本保留成功/失败退出码。Windows启动与检查均使用UTF-8，避免中文路径和日志受系统默认编码影响；这仍不等于已经Windows实机验收。

更新程序前先退出旧启动窗口。新版启动器核对HTTP服务版本，避免误用仍占着8094端口的旧版后台。接口变化记录见`BACKEND_HANDOFF.md`。

固定储备比例是仿真策略；厂家曲线不代表任意无人机电池。真实低温飞行性能未验证，不能把软件结果直接作为实飞安全决策。
