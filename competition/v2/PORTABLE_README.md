# 寒域智航：拿到包后怎么用

这是本机二维参考仿真，不控制真实无人机。

1. **先完整解压ZIP。** 不要在压缩文件预览里直接运行，也不要只复制一个启动文件。
2. **准备Python 3.12。** Windows安装时带上Python Launcher；Mac需能在终端使用`python3.12`。Python本身不在本包内。
3. Mac双击根目录「启动寒域智航.command」；Windows双击「启动Windows.bat」。首次会创建`.competition-venv`。带`wheelhouse`目录的包直接使用内置依赖，不需要联网。
4. 浏览器会打开`http://127.0.0.1:8094/`。保持启动窗口开着，点击「开始巡看」，观察调整和返程，再导出或复演。
5. 停止服务时在启动窗口按Control+C。记录在本包`runtime/missions-v2.sqlite3`，下次仍可查看；服务重启后只能从头复演。

内置依赖适用于**Python 3.12、Apple芯片Mac及64位Windows（x86-64）**。Intel Mac、Windows ARM或其他Python版本不能直接使用这套离线依赖；不要把下载了Windows依赖等同于Windows已经完成实机验证。

初次解压到另一台电脑时不要携带旧`.competition-venv`；它是机器相关环境。保留原包备份，在新目录中首次启动即可重新创建。日常记录可通过页面导出JSON；保存整个`runtime`目录前应先停止服务。

## 简单演示顺序

选择温度，看起飞前预算 → 开始巡看 → 在前方加入禁入区 → 看右侧调整原因 → 等待实际返回 → 查看记录并导出。默认20倍，仿真时间不等于现实时间；可以暂停讲解再继续。

连接中断时，画面是最后收到的状态，后台可能仍在运行；页面会重连，不会自动重发刚才的操作。遇到电量不足、超出温度范围或极端强风，会明确显示拒绝、信息不足或失败。

## 文件位置

- `competition/v2/`：程序、模型合同、测试和说明。
- `competition/data/p42a_reference.json`：带来源的低温参考参数。
- `competition/v2/evidence/`：公开实验摘要与全部逐项统计，完整遥测档案另行保存。
- `PACKAGE_MANIFEST.json`：包内文件指纹，用来核对代码、参数、说明和视频。
- `media/`：若已随包提供，为当前版本实际运行录屏及对应运行记录，不能当真人答辩视频。

在根目录可运行：`.competition-venv/bin/python -m unittest discover -s competition/v2/tests -v`；Windows将Python路径换为`.competition-venv\Scripts\python.exe`。

组员在实际比赛电脑上可双击「检查Mac.command」或「检查Windows.bat」。约一分钟完成文件指纹、依赖、软件检查、服务重启与复演，报告保存在`runtime/checks-日期时间/verification.json`。它仍不能代替实际点击、投影和PowerPoint/WPS播放检查。

固定储备比例是仿真策略；厂家曲线不代表任意无人机电池。真实低温飞行性能未验证，不能把软件结果直接作为实飞安全决策。
