# 4C演示文件生成

生成器使用bundled Node与`@oai/artifact-tool`创建18页原生可编辑PPTX。主讲12页共540秒，附录6页。页面截图必须来自实际软件，数值必须来自已保存的曲线提取和实验结果。

私有构建目录为`output/4C/.build/presentation`，交付目录为`output/4C/presentation`。构建前将本目录的`build_deck.mjs`复制到私有构建目录，并在那里创建指向bundled Node packages的`node_modules`符号链接，使用bundled Node运行。

输入JSON需要：

- `curveSummary`：`temperature_c`、`energy_wh`、`k_ratio`，包含−20、0、23℃。
- `voltageCurves`：`temperature_c`与`points`，每点含`capacity_ah`、`voltage_v`。
- `metrics`：distance与energy两条记录，包含全任务执行数、返回数、平均执行Wh，以及`completion_rate`、`return_rate`。比例为0～1。
- `comparableChart`：`categories`、`distance_wh`、`energy_wh`。仅统计相同非零完成点数且双方实际返航和储备达标的pair，不把任务少做称为节能。
- `scenarioCount`：实际冻结实验场景数。
- `screenshots.map`、`budget`、`runtime`、`result`、`events`：实际页面的区域裁切，原图来源另存于`screenshotProvenance`。先运行`crop_screens.py`，仅裁切原像素，不重绘地图或更改数字。
- `decisionExample`与`decisionBudget`：来自正式low_budget-s1原始导出的0℃/−20℃执行结果与−20℃起飞预算，不混淆预测和执行。
- `sources.competition`、`sources.molicel`：官方URL。可加入`software`、`experiment`、`curveFile`。
- `resultNarrative`、`resultCaption`与`experimentDesign`从正式结果生成。

生成器拒绝缺少事实图表、实际截图或实验指标的输入。原V3仅按发布清单与MODEL_DECISION声明的探索性证据范围使用。

字体使用官方Adobe仓库提供的思源黑体`Source Han Sans SC`。字体文件位于`output/4C/.build/fonts/SourceHanSansSC-Regular.otf`，生成器在进程内注册。为bundled LibreOffice兼容渲染，同一专用字体另已复制到用户字体目录，原字体与bundled依赖不变。字体库存注册结果必须包含该字族。

主讲只保留预算约束公式，恒定保守功率模型与LSTM细节留在附录。能量A*在每次规划中等价最短时间，不宣称原创电化学模型。两个策略共用返航规则，正式返航数量不用于声称某策略更安全。

封面使用有来源的海林雪景照片，仅作为拟定应用背景。完整署名与CC BY-SA2.0授权记录见`assets/ATTRIBUTION.md`，并复制到交付目录。

主讲逐页中文讲稿与秒数保留在PPTX speaker notes，并导出`talk.json`与`9分钟讲稿.md`。主讲时长合计540秒。`talk.json`可供明确标注的合成旁白练习使用，不能把合成语音当作学生真人演练。

尝试LibreOffice转换时，只调用bundled LibreOffice绝对路径：

`/Users/kedong/.cache/codex-runtimes/codex-primary-runtime/dependencies/bin/override/soffice`

禁止调用用户桌面安装的LibreOffice。PPTX经过skill finalizer后，生成器重新导入最终文件，逐页导出18张PNG供视觉检查。私有验证原件保留在`.build`；最终验收记录复制到`output/4C/evidence/presentation-finalization.json`，导出与逐页视觉检查记录位于`output/4C/evidence/presentation-qa.json`。

`export_pdf.py`为bundled LO指定私有`FONTCONFIG_FILE`、字体目录与缓存，先导出到`.build/presentation/pdf-export`。这是修复转换进程中文字形缺失所必需的配置；无需修改bundled运行时。其导出结果须单独检查。

本次LO仍存在三条散点曲线只显示最后一条的兼容问题。经确认，最终展示备份改由`export_preview_pdf.py`用ReportLab将已逐页核查的artifact-tool PNG原样放入18页16:9 PDF。PDF明确为图片预览；原生可编辑图表、表格和嵌入数据工作簿仍保留在最终PPTX。LO导出仅留在私有构建目录，不作为最终交付。
