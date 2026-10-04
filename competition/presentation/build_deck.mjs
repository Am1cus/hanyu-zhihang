import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Presentation, PresentationFile, FileBlob } from '@oai/artifact-tool';
import { GlobalFonts } from '@napi-rs/canvas';

const workspaceDir = path.resolve(process.env.WORKSPACE_DIR ?? process.cwd());
process.env.RUNTIME_NODE_MODULES='/Users/kedong/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules';
const SKILL_DIR = '/Users/kedong/.codex/plugins/cache/openai-primary-runtime/presentations/26.904.11930/skills/presentations';
const RUNTIME_PYTHON = '/Users/kedong/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3';
const buildDir = path.join(workspaceDir, 'output/4C/.build/presentation');
const outDir = path.join(workspaceDir, 'output/4C/presentation');
const inputPath = path.resolve(process.argv[2] ?? path.join(buildDir, 'deck-input.json'));
const input = JSON.parse(await fs.readFile(inputPath, 'utf8'));
const fontPath=path.join(workspaceDir,'output/4C/.build/fonts/SourceHanSansSC-Regular.otf');
GlobalFonts.registerFromPath(fontPath);
if(!GlobalFonts.families.some(x=>x.family==='Source Han Sans SC')) throw new Error('Source Han Sans SC was not registered');
const { resolvePresentationFont, applyPresentationChartFont, finalizePresentation } = await import(pathToFileURL(path.join(SKILL_DIR, 'container_tools/artifact_tool_utils.mjs')).href);
const FAMILY = resolvePresentationFont({ fontFamily: input.fontFamily ?? 'Source Han Sans SC' });
const C = { bg:'#F7F9F7', ink:'#28342E', pine:'#2C6653', muted:'#64766C', grid:'#DCE5DF', pale:'#E7EFEB', light:'#FFFFFF', rust:'#AF6A43' };
const W=1280, H=720;
const px = pt => pt*4/3;
const durations=[20,40,40,40,50,50,90,65,40,45,35,25];
if(durations.reduce((a,b)=>a+b,0)!==540) throw new Error('Talk must total 540 seconds');
if(!Array.isArray(input.curveSummary) || input.curveSummary.length<3) throw new Error('Measured/digitized curve summary is required');
if(!Array.isArray(input.voltageCurves) || input.voltageCurves.length<3) throw new Error('Digitized voltage curves are required');
if(!Array.isArray(input.metrics) || input.metrics.length!==2) throw new Error('Actual two-strategy metrics are required');
for(const name of ['map','budget','runtime','result','events','comparison']) if(!input.screenshots?.[name]) throw new Error(`Actual ${name} screenshot is required`);
if(input.decisionExample?.length!==2) throw new Error('Actual low-budget decision example required');
for(const r of input.metrics) for(const key of ['avg_tasks','completion_rate','return_rate']) if(!Number.isFinite(r[key])) throw new Error(`Missing actual metric ${key}`);
if(!Number.isInteger(input.scenarioCount) || input.scenarioCount<1) throw new Error('Actual scenario count is required');
if(!input.sources?.competition || !input.sources?.molicel) throw new Error('Official source URLs required');
await fs.mkdir(buildDir,{recursive:true});
await fs.mkdir(outDir,{recursive:true});
const p=Presentation.create({slideSize:{width:W,height:H}});
p.theme.colorScheme={name:'寒域智航',themeColors:{accent1:C.pine,accent2:C.muted,accent3:C.rust,accent4:'#83715D',accent5:'#799589',accent6:'#9CB1A7',bg1:C.bg,bg2:C.light,tx1:C.ink,tx2:C.muted,dk1:'#000000',dk2:C.ink,lt1:'#FFFFFF',lt2:C.pale,hlink:C.pine,folHlink:C.muted}};
const slides=[], notes=[];
const sourcenotes=(...items)=>items.filter(Boolean).join('\n');
const relpath=abs=>path.relative(workspaceDir,abs);
function tx(s,text,x,y,w,h,pt=24,color=C.ink,bold=false,align='left') {
  const obj=s.shapes.add({geometry:'textbox',name:`text-${slides.length}-${s.shapes.items?.length??0}`,position:{left:x,top:y,width:w,height:h},fill:'none',line:{fill:'none',width:0}});
  obj.text=text;
  obj.text.style={typeface:FAMILY,fontSize:px(pt),color,bold,alignment:align,verticalAlignment:'top',autoFit:'none',wrap:'square',insets:{left:0,right:0,top:0,bottom:0},lineSpacing:1.12};
  return obj;
}
function slide(title,note,sources='',appendix=false) {
  const s=p.slides.add(); s.background.fill=C.bg; slides.push(s);
  if(title) tx(s,title,72,45,1136,78,32,C.ink,true);
  tx(s,`${appendix?'附录 ':''}${String(slides.length).padStart(2,'0')}`,1160,666,64,24,13,C.muted,false,'right');
  let timing='';
  if(slides.length<=12){const seconds=durations[slides.length-1];const before=durations.slice(0,slides.length-1).reduce((a,b)=>a+b,0);const f=x=>`${Math.floor(x/60)}:${String(x%60).padStart(2,'0')}`;timing=`主讲时长 ${seconds} 秒。累计 ${f(before)} 至 ${f(before+seconds)}。\n\n`;}
  const noteText=timing+note+(sources?`\n\n来源与口径\n${sources}`:'');
  s.speakerNotes.textFrame.setText(noteText);notes.push({number:slides.length,title:title??'寒域智航',duration_seconds:slides.length<=12?durations[slides.length-1]:null,script:note,text:noteText});return s;
}
function paragraph(s,lead,body,y=168){tx(s,lead,72,y,1136,66,24,C.pine,true);tx(s,body,72,y+80,1100,300,24);}
function table(s,values,{x=72,y=158,w=1136,h=360,widths,pt=24,header=true}={}) {
  const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,values,columnWidths:widths});
  t.styleOptions={headerRow:false,bandedRows:false};t.borders.assign({style:'solid',fill:C.grid,width:1});
  for(let r=0;r<values.length;r++)for(let c=0;c<values[0].length;c++){
    const cell=t.getCell(r,c);cell.fill=r===0&&header?C.pine:(r%2===0?C.bg:C.light);
    cell.text.style={typeface:FAMILY,fontSize:px(pt),color:r===0&&header?C.light:C.ink,bold:r===0&&header,autoFit:'none',verticalAlignment:'middle',wrap:'square'};
  }
  t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({margins:{left:14,right:14,top:8,bottom:8},anchor:'center'});
  return t;
}
async function screenshot(s,name,x,y,w,h){const bytes=await fs.readFile(path.resolve(workspaceDir,input.screenshots[name]));return s.images.add({blob:bytes,contentType:'image/png',alt:`寒域智航实际软件截图区域：${name}；原始来源：${input.screenshotProvenance?.[name]??input.screenshots[name]}`,fit:'contain',position:{left:x,top:y,width:w,height:h}});}
function chart(s,type,config){const formatted={...config,series:config.series.map(r=>({...r,values:r.values?.map(v=>Number(v.toFixed(6))),xValues:r.xValues?.map(v=>Number(v.toFixed(8)))}))};const ch=s.charts.add(type,{chartFill:C.bg,plotAreaFill:C.bg,chartLine:{fill:'none',width:0},plotAreaLine:{fill:'none',width:0},...formatted});applyPresentationChartFont(ch,{fontFamily:FAMILY});return ch;}
const curve=input.curveSummary.slice().sort((a,b)=>a.temperature_c-b.temperature_c);
const chosen=curve.filter(x=>[-20,0,23].includes(x.temperature_c));
const metrics=input.metrics;
const strategyNames=metrics.map(m=>m.label??m.strategy);
const policySource=input.sources.competition;
const moliSource=input.sources.molicel;
const dataSource=input.sources.curveFile??'厂家曲线经数值提取，原始曲线与提取点保留在项目数据目录';

{
const s=slide(null,'各位评委好，我们的作品是寒域智航。面向东北冰雪景区，我们研究一个直观问题：天气变冷以后，这次巡检还能做几个点，能不能回到基地？下面用一个实际运行的软件案例说明。',sourcenotes(policySource,'场景为拟定应用场景，景区需求、团队署名和下一届申报资格尚待学生核对','雪景仅为应用背景，非团队实地调查或飞行取证。Felix Guan, Snow scenery of Hailin City, Heilongjiang, 2011-02-06. https://commons.wikimedia.org/wiki/File:Snow_scenery_of_Hailin_City,_Heilongjiang.jpg https://www.flickr.com/photos/magicgyp/5438563181/ CC BY-SA2.0 https://creativecommons.org/licenses/by-sa/2.0/ 原JPEG不变，仅PPT缩放/页面裁切。'));
tx(s,'寒域智航',72,182,536,92,42,C.pine,true);
tx(s,'东北冰雪景区无人机巡检\n任务决策与仿真验证平台',72,296,536,138,24,C.ink);
tx(s,'先留回程，再做巡检',72,502,536,50,24,C.pine,true);
const snow=await fs.readFile(path.join(workspaceDir,'learn/competition/presentation/assets/hailin-snow-felix-guan.jpg'));
s.images.add({blob:snow,contentType:'image/jpeg',alt:'Felix Guan拍摄的黑龙江海林雪景，CC BY-SA2.0。仅作应用背景，非团队现场取证。',fit:'cover',position:{left:648,top:150,width:560,height:420}});
tx(s,'雪景：Felix Guan / CC BY-SA 2.0',648,608,560,28,14,C.muted);
}
{
const s=slide('面向东北冰雪，关注低温任务','为什么选择东北冰雪景区？国家发展改革委公布的东北冰雪经济实施方案，提出提升冰雪旅游品质、服务水平和设施安全风险防范，实施期至二零二七年。二零二六年政府工作报告提出发展低空经济等新兴支柱产业。因此，我们选择景区巡检任务预演作为拟定应用场景。政策提供选题背景，具体巡检需求仍需由学生与景区核对。',sourcenotes(input.sources.iceEconomy,input.sources.governmentReport,input.sources.governmentReportVerifiedMirror,'政策是选题背景，不构成本软件的官方背书。尚无真实用户访谈或景区合作确认。'));
table(s,[['官方依据','选题关联'],['东北冰雪经济实施方案\n实施期至2027年','提升旅游品质与服务水平\n防范设施安全风险'],['2026年政府工作报告','发展低空经济等新兴支柱产业']],{h:324,widths:[500,636]});
tx(s,'拟定应用：东北冰雪景区的巡检任务预演',72,535,1100,56,24,C.pine,true);
tx(s,'来源：国家发展改革委实施方案；2026年政府工作报告',72,638,1090,28,14,C.muted);
}
{
const s=slide('三个点之后，还要回到基地','这是我们拟定的巡检任务：从基地出发，按顺序到三个点，每个点停留十秒，最后返回基地。三个点可以代表景区中待查看的设施，但这张地图没有对应真实景区。我们把任务顺序固定，让评委先关注一个问题：条件改变后，是继续下一个点，还是减少任务并返回？地图采用二维网格和固定高度，不包含拍照识别。',sourcenotes(input.sources.software,input.screenshotProvenance.map,'normal-s1：start [1,7]，targets [[12,3],[19,7],[12,11]]，cell_size_m80，dwell_s10，fixed_height_m40。'));
table(s,[['任务阶段','要做什么'],['从基地出发','到第一个巡检点'],['依次巡检三点','每点停留10秒'],['返回基地','到达后才记作返回']],{w:446,h:344,widths:[210,236]});
await screenshot(s,'map',554,154,654,414);
tx(s,'基地 → 点1 → 点2 → 点3 → 基地',554,588,654,48,24,C.pine,true);
tx(s,'拟定场景 · 单架虚拟无人机 · 固定任务顺序',72,636,1100,44,20,C.muted);
}
{
const s=slide('每次出发，都算三笔账','把软件的判断看成三笔账，比较容易理解。第一笔是做巡检要花的能量，第二笔是返回基地要花的能量，第三笔是保留的储备。出发前，软件把整轮三点任务一起算；运行中，每次去下一点前都重新算。右边是实际软件预算页面。条件变化后，预算也会更新。运行结束以后，可以查看轨迹、判断原因和操作记录，并导出完整档案。',sourcenotes(input.screenshotProvenance.budget,input.sources.demoExport,'真实软件截图，无数值改写。Wh为能量，三项预算不可与Ah混用。储备是声明的仿真策略参数。'));
tx(s,'① 巡检要花多少',72,169,350,64,24,C.pine,true);
tx(s,'② 回来要花多少',72,288,350,64,24,C.pine,true);
tx(s,'③ 还要留下多少',72,407,350,64,24,C.pine,true);
tx(s,'起飞前算整轮\n途中算下一点与返程',72,526,350,99,24);
await screenshot(s,'budget',464,152,744,450);
tx(s,'实际页面 · −20℃低初始能量案例',464,622,744,45,18,C.muted);
}
{
const s=slide('低温会减少参考可用能量','低温影响的依据是公开厂家曲线。我们把Molicel P42A的电压和容量曲线积分，得到参考可用能量。图中以二十三摄氏度为基准，零摄氏度约剩百分之九十四点五，负二十摄氏度约剩百分之八十六点三。负十摄氏度由相邻温度曲线插值得到。原始数据和计算代码都保留。这里仅适用于指定电芯、四点二安培恒流条件，不能代替真实无人机电池测试。',sourcenotes(moliSource,dataSource,'Molicel P42A：4.2 A恒流放电，2.5 V截止，在23°C以CC-CV充至4.2 V。温度指模型电芯温度。'));
chart(s,'bar',{position:{left:72,top:154,width:756,height:415},categories:chosen.map(x=>`${x.temperature_c}℃`),series:[{name:'相对23℃可用能量',values:chosen.map(x=>x.k_ratio),valuesFormatCode:'0.0%',fill:C.pine}],barOptions:{direction:'column',grouping:'clustered',gapWidth:90},hasLegend:false,xAxis:{textStyle:{fontSize:26,fill:C.ink},line:{fill:C.grid,width:1}},yAxis:{min:0,max:1.1,majorUnit:0.25,numberFormatCode:'0%',textStyle:{fontSize:22,fill:C.muted},majorGridlines:{fill:C.grid,width:1},title:{text:'相对可用能量',textStyle:{fontSize:26,fill:C.ink}}},dataLabels:{showValue:true,position:'outEnd',textStyle:{fontSize:28,fill:C.ink},showPercent:false}});
tx(s,'厂家曲线积分',882,181,310,76,24,C.pine,true);
tx(s,'4.2 A恒流\n2.5 V截止\n23℃作为基准',882,281,310,195,24,C.ink);
tx(s,'−10℃：归一容量节点插值电压，再积分Wh',72,585,1100,48,24,C.pine,true);
tx(s,'只适用于指定虚拟电芯的参考恒流条件',72,639,1100,44,24,C.muted);
}
{
const s=slide('同一任务，低温下减少巡检点','同一地图，初始SOC都为百分之五十五，只改变温度。零摄氏度实际完成三点并返回，负二十摄氏度完成一点并返回。负二十摄氏度可用约二十七点一九瓦时，整轮预算需要二十九点六八瓦时。初始预算按四点二伏上限算，实际曲线电压较低。途中按剩余能量逐点重算，所以零摄氏度初始支持两点，最终完成三点。表中预算和执行结果必须分开看，任务少做了也不能称为节能。',sourcenotes(input.sources.experiment,input.screenshotProvenance.comparison,'同一low_budget-s1，energy策略，initial_soc0.55（容量比例，并非Wh占比），reserve_fraction0.2；上方与截图中的预算为初始整轮预算，3/3及1/3为完整软件预演实际结果。'));
tx(s,'同一地图 · 初始SOC均为55% · 三点往返预算29.68 Wh',72,154,1136,58,24,C.pine,true);
table(s,[['温度','起飞可用能量','初始预算支持','实际执行结果'],['0℃','29.65 Wh','2点','3 / 3点，已返回'],['−20℃','27.19 Wh','1点','1 / 3点，已返回']],{y:257,h:258,widths:[180,285,290,381]});
tx(s,'初始预算较保守，实际运行逐点重算',72,554,1136,53,24,C.pine,true);
tx(s,'任务量不同，耗能下降不能称为节能',72,618,1136,48,24,C.muted);
}
{
const s=slide('看一次“完成一点后返回”','下面用九十秒看一次实际任务。先看同一任务的两个温度：零摄氏度完整软件预演是三点，负二十摄氏度是一点，两者都返回。负二十摄氏度的初始预算显示，三点巡检加返程和储备超过当前可用能量。现在点击运行这个案例，保持二十倍仿真速度，位置来自后端执行状态。到达第一个点并停留之后，系统自动判断下一点和返程预算不足，转为返回。我们没有用取消按钮模拟返航。到达基地以后，打开档案，可以看到完成一点、返回回收点为是，判断原因和原始遥测都可导出。屏幕上的秒数是仿真时间，这不是实际无人机飞行。',sourcenotes(input.sources.demoExport,input.screenshotProvenance.runtime,input.screenshotProvenance.result,'实际UI运行f1f556a8-58e5-460c-8d27-c4aff4e784af：low_budget-s1，−20℃，energy，initial_soc0.55，20倍速；1/3点、returned=true，耗能8.196377Wh。截图时暂停，仅为取证，不构成返航控制。'));
await screenshot(s,'runtime',72,150,760,436);
tx(s,'1  同一任务，比较温度\n\n2  运行 −20℃案例\n\n3  看自动转为返程\n\n4  到达基地，复查原因',874,160,334,390,24,C.pine,true);
await screenshot(s,'result',72,599,1136,75);
}
{
const resultNote='为了检查表现，我们冻结四类场景：正常、低初始能量、突风和动态障碍。每类两个固定场景，分别在零、负十和负二十摄氏度运行，每个场景比较两种路线策略，共四十八次执行。四十八次都实际返回基地，其中四十四次完成三个点，四次完成部分任务后返回。部分任务并没有被算作完整巡检。两种策略都遵守相同返程规则，不能凭这组共同返回的结果宣称能量策略更安全。这些是给定模型和固定场景下的结果，完整配置、轨迹和失败边界另存为档案。';
const s=slide('48次返回，44次完成三点',resultNote,sourcenotes(input.sources.experiment,'正式24个场景×2种策略；4次部分任务属于48次返回中的子集，不是额外执行。相同估算器、储备、信息，仅替换路线目标。'));
const total=input.aggregate.execution_count, full=input.aggregate.full_task_executions, returned=input.aggregate.returned_executions;
chart(s,'bar',{position:{left:72,top:155,width:806,height:416},categories:['完成三个点','部分巡检后返回','实际返回基地'],series:[{name:'执行次数',values:[full,total-full,returned],valuesFormatCode:'0',fill:C.pine}],barOptions:{direction:'bar',grouping:'clustered',gapWidth:90},hasLegend:false,xAxis:{textStyle:{fontSize:24,fill:C.ink},line:{fill:C.grid,width:1}},yAxis:{min:0,max:50,majorUnit:10,numberFormatCode:'0',textStyle:{fontSize:22,fill:C.muted},majorGridlines:{fill:C.grid,width:1}},dataLabels:{showValue:true,position:'outEnd',textStyle:{fontSize:30,fill:C.ink}}});
tx(s,'24个固定场景',914,169,290,60,24,C.pine,true);
tx(s,'× 2种路线策略\n= 48次执行',914,270,290,150,24);
tx(s,'44 + 4 = 48',914,464,290,65,24,C.pine,true);
tx(s,'部分任务未算作完整巡检 · 全部原始记录保留',72,612,1136,54,24,C.muted);
}
{
const s=slide('信息不足或模型失效，给出原因','正式四十八次执行没有失败，但我们另做了边界例。突发侧风达到每秒六米，超过每秒五米的固定空速模型，执行器在零点五秒记录失败。缺少参考曲线时，软件返回不可用，不生成预算。这些边界例单独保存，不混入正式场景分母。它们说明软件能记录信息不足与模型失效，真实飞行安全仍需独立验证。',sourcenotes('output/4C/evidence/boundaries/report.json','output/4C/evidence/boundaries/sudden_crosswind_failure.json','output/4C/evidence/boundaries/missing_reference.json'));
table(s,[['实际边界例','软件记录'],['突发6 m/s侧风','执行失败：轨迹保持模型失效'],['缺少参考曲线','参数不可用：不生成预算']],{h:284,widths:[455,681]});
tx(s,'边界例单独保存，未计入正式48次执行',72,523,1100,56,24,C.pine,true);
tx(s,'真实飞行安全仍待独立验证',72,602,1100,52,24,C.muted);
}
{
const s=slide('变化之后，重新核算返程','路线搜索采用已有的A星算法。作品的特色是把任务中需要考虑的四件事接在一起。第一，顺风和逆风让同一路段的去程与返程代价不同。第二，每次去下一点，都独立核算回到起点的路线。第三，风场或障碍改变以后，按当前观测重新判断。第四，保留参数、轨迹、事件与决策理由。两种规划遵守相同预算和信息条件，其他人可以复查差异来自哪里。',input.sources.software);
table(s,[['实现特点','对任务预演的作用'],['考虑风向','同一路段的去程与返程代价可不同'],['独算返程','每次去下一点，都核算回收路线'],['条件变化后重算','风场或障碍改变，重新判断'],['保留运行档案','保存参数、轨迹与决策理由']],{h:392,widths:[360,776]});
tx(s,'A*为基础方法，本作贡献是任务流程与证据组织',72,602,1100,55,24,C.muted);
}
{
const s=slide('真实操作已开始，验证继续补足','组员提交了Windows操作截图和四份档案，已逐份核验与复算。它们包含两份不同完整内容、一份重复结果和一份取消记录，不计入正式实验。编程和材料使用智能工具辅助；两名学生仍需完成需求核对、代码理解和真人演练。当前飞行结果都是软件仿真。',sourcenotes('output/4C/evidence/team/20261004/audit.md','output/4C/evidence/team/20261004/audit.json','4个档案重算/当前核心复现，11个提交文件哈希匹配；不证明截图与每个UUID绑定、旧复演按钮来源或干净Windows重装。'));
table(s,[['当前证据','完成情况'],['软件与实验','本机可运行；48次正式记录可复查'],['组员实际操作','Windows截图、4份档案已提交并核验'],['学生接下来的任务','需求核对、理解代码、试用与真人演练']],{h:354,widths:[300,836]});
tx(s,'工具辅助实现与材料制作 · 飞行结果均为软件仿真',72,594,1136,55,24,C.muted);
}
{
const s=slide('把每次取舍，变成能复查的记录','寒域智航把巡检中的取舍，变成看得懂、跑得出、查得到的软件记录。条件变了，先核算下一点和回程，再决定继续还是返回。后续核对真实需求，补独立低温数据和飞行验证。谢谢各位评委。',sourcenotes(policySource,input.sources.software));
tx(s,'先留回程，再做巡检',72,182,1136,88,36,C.pine,true);
tx(s,'看得懂：完成几个点，是否到达基地\n跑得出：同一条件可以重新执行\n查得到：参数、轨迹和判断原因保留',72,327,1136,206,24);
tx(s,'后续：核对需求，补独立低温数据与真实飞行验证',72,604,1136,58,24,C.muted);
}
{
const s=slide('需求与政策来源','答辩参考。作品按官方软件应用与开发中的算法设计与应用方向准备，下一届具体要求须再核对。国家发展改革委公布的冰雪经济政策为应用选题背景，政府工作报告提供相关发展方向的公开依据。这些政策不等于真实景区需求确认，也不代表我们已获得合作。需求状态仍为拟定场景。',sourcenotes(input.sources.competition,'https://www.ndrc.gov.cn/xxgk/zcfb/ghwb/202412/P020241205581474196116.pdf','https://www.npc.gov.cn/c2/c30834/202603/t20260316_453264.html','尚无实地采访、合作确认或用户试用记录。'),true);
table(s,[['官方资料','在本作中的用途'],['4C软件应用与开发分类','算法设计与应用方向'],['冰雪经济政策文件','东北冰雪景区的选题背景'],['2026年政府工作报告','公开发展方向参考'],['实际需求核对','待学生完成，无采访背书']],{h:391,widths:[474,662],pt:20});
tx(s,'政策背景与真实用户需求分别核对',72,609,1100,50,20,C.muted);
}
{
const s=slide('厂家曲线的数值提取','答辩参考。绘图点来自厂家PDF的电压—容量曲线，采用梯形积分计算Wh，并保留坐标、处理代码与源文件。图中为提取点的原生可编辑图表。提取分辨率会影响积分，因此结果使用有限有效数字，并按同一截止条件比较。',sourcenotes(moliSource,dataSource),true);
chart(s,'scatter',{position:{left:72,top:150,width:786,height:444},series:input.voltageCurves.filter(x=>[-20,0,23].includes(x.temperature_c)).map((r,i)=>({name:`${r.temperature_c}℃`,xValues:r.points.map(v=>v.capacity_ah),values:r.points.map(v=>v.voltage_v),line:{fill:[C.rust,C.muted,C.pine][i],width:2.5},marker:{symbol:'none'}})),scatterOptions:{style:'line'},hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:22,fill:C.ink}},xAxis:{title:{text:'放电容量／Ah',textStyle:{fontSize:24,fill:C.ink}},numberFormatCode:'0.0',textStyle:{fontSize:22,fill:C.muted},majorGridlines:null},yAxis:{min:2.4,max:4.3,title:{text:'电压／V',textStyle:{fontSize:24,fill:C.ink}},numberFormatCode:'0.0',textStyle:{fontSize:22,fill:C.muted},majorGridlines:{fill:C.grid,width:1}}});
table(s,[['温度','能量／Wh'],...chosen.map(x=>[`${x.temperature_c}℃`,x.energy_wh.toFixed(2)])],{x:908,y:205,w:288,h:259,widths:[120,168],pt:20});
tx(s,'指定恒流条件下的\n参考单电芯曲线',907,511,290,90,20,C.muted);
}
{
const s=slide('规划目标与任务预算','答辩参考。距离A星按航段距离优化。能量A星使用恒定保守功率乘航段时间，在每次规划中严格等价于最短时间目标，这是声明的简化，不是原创电化学能耗模型。二者共用四邻域地图、当前风场和预算规则。起飞前计算整轮既定任务与回到起点的预算，并给出可完成前缀。在线守卫只检查当前到下一点的去程、驻留、返航与储备，不读取未来事件。',input.sources.software,true);
table(s,[['计算项','采用方法'],['距离A*','优化路径距离'],['能量A*','70.56 W恒功率×时间，等价最短时间'],['整轮预演','既定三点与返航预算，可完成前缀'],['在线守卫','下一点与返航、20%参考储备'],['执行评价','4S1P，4.2 A，曲线电压积分']],{h:409,widths:[317,819],pt:20});
tx(s,'返程单独规划，任务顺序固定',72,613,1110,48,20,C.pine,true);
}
{
const s=slide('全量结果与单独边界例','答辩参考。正式二十四场景、四十八次执行中，每种规划都有二十四次返航和二十二次完成全部三点，正式失败数为零。平均执行耗能保留原始Wh，配对百分比差单独计算，不能把平均值之差替代平均配对差。另做的边界例包括突发侧风失败、参考曲线缺失、温度不覆盖和首点阻塞，全部排除在正式分母之外。',sourcenotes(input.sources.experiment,'output/4C/evidence/boundaries/report.json'),true);
table(s,[['规划','完整三点','返航','平均执行Wh'],...metrics.map(x=>[x.label??x.strategy,`${x.full_task_count} / 24`,`${x.returned_count} / 24`,x.mean_wh.toFixed(3)])],{h:251,widths:[285,258,243,350],pt:20});
tx(s,'同工作量24对：平均配对参考耗能差1.59%',72,459,1100,50,20,C.pine,true);
tx(s,'正式48次：0失败，4次部分任务后返回；不推断实飞节能',72,507,1100,50,20,C.muted);
tx(s,'另存4个边界例：失败、缺曲线、温度不覆盖、首点阻塞',72,570,1110,70,20,C.muted);
}
{
const s=slide('V3证据的适用范围','答辩参考。V3发布清单明确记录研究状态为选型后候选，尚待独立确认。原晋级门槛没有通过，项目验收没有通过，真实数据验证和在线部署切换也没有发生。本次用冻结运行时成功执行原示例请求，十秒预测耗电约零点零四零九六安时，历史基线约零点零三七零八安时。请求没有未来标签，所以没有计算准确率。真实调用证实代码可以执行，独立准确度确认仍待新数据。',sourcenotes('learn/Phase4/releases/energy_residual_lstm_v3_rc1/manifest.json','learn/Phase4/releases/energy_residual_lstm_v3_rc1/MODEL_DECISION.md','output/4C/evidence/lstm_actual_response.json'),true);
table(s,[['证据','当前状态'],['标签来源','AIRSIM_FORMULA_BATTERY'],['模型选型','查看候选结果后的探索性选择'],['独立最终确认','待完成'],['真实低温与真实飞行','尚未验证'],['在线模型切换','未发生']],{h:360,widths:[386,750],pt:20});
tx(s,'本次真实调用：10秒预测0.04096 Ah，历史基线0.03708 Ah',72,554,1110,44,20,C.pine,true);
tx(s,'无未来标签，不计算准确率',72,612,1110,44,20,C.muted);
}
{
const s=slide('复现与贡献说明','答辩参考。交付包提供软件源码、已构建网页、启动脚本、曲线来源与提取记录，以及正式和边界实验档案。按README在本机启动后，用同一参数可以复查记录与复演。编程、实验整理与材料制作使用智能工具辅助，学生的需求核对、理解、同学试用和现场真人演练须真实完成后登记。一万元分配为预算上限，详见预算文档，未填写未发生的支出。',sourcenotes('learn/competition/README.md','learn/competition/BUDGET.md','learn/competition/STUDENT_TASKS.md','智能工具辅助编程与材料，学生真实贡献按完成记录填写。'),true);
table(s,[['记录类别','证据与边界'],['软件与参数','源码、构建网页、P42A源PDF与提取点'],['仿真证据','正式48次、边界4例、336次敏感性执行'],['组员实际操作','4份提交档案已核验；不是4次独立完整试验'],['本版操作记录','暂停、继续、取消、复演来源单独保存'],['旧版档案','无操作历史则标记未知，不补造记录']],{h:413,widths:[350,786],pt:20});
tx(s,'需求核对、学生理解与真人演练仍需实际完成并登记',72,613,1110,49,20,C.muted);
}

if(slides.length!==18) throw new Error(`Expected 18 slides, got ${slides.length}`);
const stamp=new Date().toISOString().replace(/[-:.]/g,'').slice(0,15);
const candidatePath=path.join(buildDir,`candidate-${stamp}.pptx`);
await (await PresentationFile.exportPptx(p)).save(candidatePath);
await fs.writeFile(path.join(buildDir,'speaker-notes.json'),JSON.stringify(notes,null,2));
await fs.writeFile(path.join(outDir,'talk.json'),JSON.stringify({title:'寒域智航',total_seconds:540,narration_disclosure:'可供合成旁白练习使用。合成语音不代表学生真人演练。',slides:notes.slice(0,12).map(n=>({title:n.title,seconds:n.duration_seconds,script:n.script}))},null,2));
await fs.writeFile(path.join(outDir,'9分钟讲稿.md'),notes.map(n=>`## ${n.number}. ${n.title}\n\n${n.text}\n`).join('\n'));
await fs.copyFile(path.join(workspaceDir,'learn/competition/presentation/assets/ATTRIBUTION.md'),path.join(outDir,'素材署名.md'));
const FINAL_PPTX=path.join(outDir,`寒域智航_4C_18页_${stamp}.pptx`);
const tableOwners=[2,3,6,9,10,11,13,14,15,16,17,18];
const result=await finalizePresentation({workspaceDir,candidatePath,finalPath:FINAL_PPTX,explicitTotalSlideCount:18,requiredNativeTableOwnerSlides:tableOwners,requiredNativeChartOwnerSlides:[5,8,14],materializeLiteralChartWorkbooks:true,pythonExecutable:RUNTIME_PYTHON,integrityValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_package_integrity.py'),layoutValidatorPath:path.join(SKILL_DIR,'container_tools/inspect_presentation_layout_geometry.py'),layoutArgs:['--expected-slide-size-emu','12192000,6858000','--validate-heading-fit','--validate-bullet-geometry',...tableOwners.flatMap(x=>['--require-native-table-slide',String(x)])],fontPolicy:{basis:'design',families:[FAMILY]},verifyArtifactToolImport:true,receiptPath:path.join(buildDir,`${path.basename(FINAL_PPTX)}.validation.json`)});
const final=await PresentationFile.importPptx(await FileBlob.load(FINAL_PPTX));
const pngDir=path.join(outDir,'slides');await fs.mkdir(pngDir,{recursive:true});
for(let i=0;i<18;i++){
 const s=final.slides.getItem(i);const png=await final.export({slide:s,format:'png',scale:1});
 await fs.writeFile(path.join(pngDir,`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await png.arrayBuffer()));
 const layout=await s.export({format:'layout'});await fs.writeFile(path.join(buildDir,`slide-${String(i+1).padStart(2,'0')}.layout.json`),await layout.text());
}
await fs.writeFile(path.join(buildDir,'build-result.json'),JSON.stringify({pptx:FINAL_PPTX,pngDir,fontFamily:FAMILY,inputPath,slideCount:18,talkSeconds:540,validation:result},null,2));
console.log(JSON.stringify({pptx:FINAL_PPTX,pngDir,fontFamily:FAMILY,slideCount:18,talkSeconds:540}));
