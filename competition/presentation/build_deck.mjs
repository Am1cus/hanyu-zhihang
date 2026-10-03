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
for(const name of ['map','budget','runtime','result','events']) if(!input.screenshots?.[name]) throw new Error(`Actual ${name} screenshot is required`);
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
const s=slide(null,'各位评委好，我们的作品是寒域智航，面向东北冰雪景区的巡检任务预演。软件把低温能量、风场和返航储备纳入任务决策，再通过本机仿真展示结果。接下来介绍实际软件流程与可复查的证据。',sourcenotes(policySource,'场景为拟定应用场景，景区需求、团队署名和下一届申报资格尚待学生核对','雪景仅为应用背景，非团队实地调查或飞行取证。Felix Guan, Snow scenery of Hailin City, Heilongjiang, 2011-02-06. https://commons.wikimedia.org/wiki/File:Snow_scenery_of_Hailin_City,_Heilongjiang.jpg https://www.flickr.com/photos/magicgyp/5438563181/ CC BY-SA2.0 https://creativecommons.org/licenses/by-sa/2.0/ 原JPEG不变，仅PPT缩放/页面裁切。'));
tx(s,'寒域智航',72,182,536,92,42,C.pine,true);
tx(s,'东北冰雪景区无人机巡检\n任务决策与仿真验证平台',72,296,536,138,24,C.ink);
tx(s,'本机任务预演软件',72,502,536,50,24,C.muted);
const snow=await fs.readFile(path.join(workspaceDir,'learn/competition/presentation/assets/hailin-snow-felix-guan.jpg'));
s.images.add({blob:snow,contentType:'image/jpeg',alt:'Felix Guan拍摄的黑龙江海林雪景，CC BY-SA2.0。仅作应用背景，非团队现场取证。',fit:'cover',position:{left:648,top:150,width:560,height:420}});
tx(s,'雪景：Felix Guan / CC BY-SA 2.0',648,608,560,28,14,C.muted);
}
{
const s=slide('政策提供选题背景，需求还需核对','为什么选择东北冰雪景区？国家发展改革委公布的东北冰雪经济实施方案，提出提升冰雪旅游品质、服务水平和设施安全风险防范，实施期至二零二七年。二零二六年政府工作报告提出发展低空经济等新兴支柱产业。因此，我们选择景区巡检任务预演作为拟定应用场景。政策提供选题背景，具体巡检需求仍需由学生与景区核对。',sourcenotes(input.sources.iceEconomy,input.sources.governmentReport,input.sources.governmentReportVerifiedMirror,'政策是选题背景，不构成本软件的官方背书。尚无真实用户访谈或景区合作确认。'));
table(s,[['官方依据','选题关联'],['东北冰雪经济实施方案\n实施期至2027年','提升旅游品质与服务水平\n防范设施安全风险'],['2026年政府工作报告','发展低空经济等新兴支柱产业']],{h:324,widths:[500,636]});
tx(s,'拟定应用：东北冰雪景区的巡检任务预演',72,535,1100,56,24,C.pine,true);
tx(s,'来源：国家发展改革委实施方案；2026年政府工作报告',72,638,1090,28,14,C.muted);
}
{
const s=slide('从基地出发，依次巡检三点再返回','以软件中的正常巡检场景一为例。无人机从坐标一、七的基地出发，依次到十二、三，十九、七，十二、十一三个巡检点，每点驻留十秒，最后回到基地。地图每格八十米，固定高度四十米。三个点按既定顺序执行，软件只规划各段路线。这里的地图和坐标是拟定仿真场景，后续可以在需求核对后替换，当前没有真实景区地理背书。',sourcenotes(input.sources.software,input.screenshotProvenance.map,'normal-s1：start [1,7]，targets [[12,3],[19,7],[12,11]]，cell_size_m80，dwell_s10，fixed_height_m40。'));
table(s,[['步骤','坐标','动作'],['基地','(1,7)','起飞'],['点1','(12,3)','停10秒'],['点2','(19,7)','停10秒'],['点3','(12,11)','停10秒'],['返程','(1,7)','回收']],{w:446,h:432,widths:[116,158,172]});
await screenshot(s,'map',554,177,654,365);
tx(s,'基地 → 点1 → 点2 → 点3 → 基地',554,570,654,48,24,C.pine,true);
tx(s,'拟定仿真地图，非真实景区坐标',72,637,1080,44,24,C.muted);
}
{
const s=slide('任务前、任务中、任务后都有记录','软件分为三个工作阶段。任务前，输入条件，比较两种规划，查看整轮任务预算。右侧是负二十摄氏度实际页面的预算区域，三点巡检、返程和储备分别显示。任务中，后端推进轨迹，风场或障碍改变后重新判断。任务后，复查结果和决策，并导出运行档案。这三个阶段已经接入同一本机软件。截图来自实际操作，全部仍是仿真结果。',sourcenotes(input.screenshotProvenance.budget,input.sources.demoExport,'真实软件截图，仅裁切区域，没有重新绘制或改写数值。'));
tx(s,'任务前\n比较策略、检查预算',72,169,330,100,24,C.pine,true);
tx(s,'任务中\n运行、改变条件、重算',72,326,360,100,24);
tx(s,'任务后\n复查决策、导出档案',72,483,360,100,24);
await screenshot(s,'budget',438,176,770,355);
tx(s,'实际页面：−20℃，整轮预算含返程与储备',438,568,770,74,24,C.muted);
}
{
const s=slide('低温会减少参考可用能量','低温的影响来自公开厂家曲线。我们提取Molicel P42A原始PDF的电压和容量坐标，积分成可用能量。与二十三摄氏度相比，零摄氏度约为百分之九十四点五，负二十摄氏度约为百分之八十六点三。负十摄氏度先在归一化容量节点上插值电压，再积分能量。参数仅适用于这款虚拟电芯和厂家四点二安培恒流条件，高倍率、自热和老化还需要独立验证。',sourcenotes(moliSource,dataSource,'Molicel P42A：4.2 A恒流放电，2.5 V截止，在23°C以CC-CV充至4.2 V。温度指模型电芯温度。'));
chart(s,'bar',{position:{left:72,top:154,width:756,height:415},categories:chosen.map(x=>`${x.temperature_c}℃`),series:[{name:'相对23℃可用能量',values:chosen.map(x=>x.k_ratio),valuesFormatCode:'0.0%',fill:C.pine}],barOptions:{direction:'column',grouping:'clustered',gapWidth:90},hasLegend:false,xAxis:{textStyle:{fontSize:26,fill:C.ink},line:{fill:C.grid,width:1}},yAxis:{min:0,max:1.1,majorUnit:0.25,numberFormatCode:'0%',textStyle:{fontSize:22,fill:C.muted},majorGridlines:{fill:C.grid,width:1},title:{text:'相对可用能量',textStyle:{fontSize:26,fill:C.ink}}},dataLabels:{showValue:true,position:'outEnd',textStyle:{fontSize:28,fill:C.ink},showPercent:false}});
tx(s,'厂家曲线积分',882,181,310,76,24,C.pine,true);
tx(s,'4.2 A恒流\n2.5 V截止\n23℃作为基准',882,281,310,195,24,C.ink);
tx(s,'−10℃：归一容量节点插值电压，再积分Wh',72,585,1100,48,24,C.pine,true);
tx(s,'只适用于指定虚拟电芯的参考恒流条件',72,639,1100,44,24,C.muted);
}
{
const s=slide('低温让同一次任务需要缩减巡检点','预算规则只有一句话：执行、返航和储备所需能量，不能超过当前可用能量。看正式实验中的低预算场景一。同一地图、百分之五十五初始容量，负二十摄氏度可用二十七点一九瓦时，而整轮三点需要二十九点六八瓦时，所以起飞预算预计只能完成第一个点。下表列的是执行结果：零摄氏度完成三点后返回，负二十摄氏度完成一点后返回。后者任务少做了，不能把耗能下降称为节能。途中每次去下一点前，软件还会重新核验预算。',sourcenotes(input.sources.software,input.sources.experiment,'output/4C/evidence/formal/runs/low_budget-s1-t-20-energy.json','正式low_budget-s1能量策略，initial_soc0.55。上方为实际起飞预算，下表为执行结果；理想4S1P恒流参考模型，不构成真实飞行保证。'));
tx(s,'执行能量 + 返航能量 + 储备 ≤ 可用能量',72,157,1136,62,24,C.pine,true);
tx(s,`−20℃、55%容量：可用${input.decisionBudget.available_wh.toFixed(2)} Wh，三点需${input.decisionBudget.required_wh.toFixed(2)} Wh`,72,246,1136,48,24);
tx(s,`当前预算预计${input.decisionBudget.feasible_prefix_count}点；下表为同一场景的实际执行结果`,72,301,1136,48,24,C.pine);
table(s,[['温度','完成巡检','回收点','参考耗能'],...input.decisionExample.map(r=>[`${r.temperature_c}℃`,`${r.visited_count} / ${r.target_count}点`,r.returned?'已返回':'未返回',`${r.total_energy_wh.toFixed(2)} Wh`])],{y:368,h:216,widths:[180,380,260,316]});
tx(s,'−20℃少做了任务，不能把耗能下降称为节能',72,617,1100,52,24,C.muted);
}
{
const s=slide('90秒演示：预算、重算与导出','现在演示实际工作流。第一步，查看零摄氏度与负二十摄氏度的预算。同一正常巡检场景，当前可用能量分别约五十六点九九与五十二点零八瓦时，整轮预算都含三个巡检点、返程和储备。第二步，启动负十摄氏度的能量策略，后端推进位置和耗能。第三步，在运行中暂停，在地图上手动增加一个障碍，再继续运行。左图可以看到路线绕开新增障碍；事件和重新判断进入档案。最后进入结果复查，查看三个巡检点完成、已返回回收点，参考模型耗能约十六点一八瓦时，并导出JSON。我们还可以核对事件参数和决策时间。这些操作已在实际页面完成，现场演示仍限于本机仿真。',sourcenotes(...Object.values(input.screenshotProvenance),input.sources.demoExport,'新真实UI导出：mission-6d454f77-a255-4737-a791-455985436c2a。正式24场景统计与本次手动操作档案分别保存。'));
await screenshot(s,'runtime',72,157,720,421);
tx(s,'1  查看两种温度预算\n\n2  启动任务\n\n3  手动加障碍、重算\n\n4  复查并导出记录',847,173,361,380,24,C.pine,true);
await screenshot(s,'result',72,584,1080,101);
}
{
const resultNote=input.resultNarrative??`本次实验运行了${input.scenarioCount}个冻结场景，每个场景分别执行距离A星与能量A星。两种策略使用相同估算器、储备门槛和当前观测，只替换路线目标。耗能图只统计双方完成相同非零任务、实际返航并满足储备的场景。减少任务量带来的耗能下降不能称为节能，结果也不代表真实飞行。`;
const s=slide('48次均返航，44次完成三个点',resultNote,sourcenotes(input.sources.experiment??'本次固定场景实验结果','两策略统一估算器、储备和当前观测，仅路线objective替换。耗能比较限相同非零任务量且双方实际返航与储备达标的pair。'));
if(!input.comparableChart?.categories?.length) throw new Error('Comparable executed-energy chart is required');
chart(s,'bar',{position:{left:72,top:155,width:790,height:408},categories:input.comparableChart.categories,series:[{name:'距离A*',values:input.comparableChart.distance_wh,valuesFormatCode:'0.00',fill:C.muted},{name:'能量A*',values:input.comparableChart.energy_wh,valuesFormatCode:'0.00',fill:C.pine}],barOptions:{direction:'column',grouping:'clustered',gapWidth:65},hasLegend:true,legend:{position:'bottom',textStyle:{fontSize:24,fill:C.ink}},xAxis:{textStyle:{fontSize:23,fill:C.ink},line:{fill:C.grid,width:1}},yAxis:{min:0,numberFormatCode:'0.0',textStyle:{fontSize:22,fill:C.muted},majorGridlines:{fill:C.grid,width:1},title:{text:'执行耗能／Wh',textStyle:{fontSize:26,fill:C.ink}}},dataLabels:{showValue:true,position:'outEnd',textStyle:{fontSize:25,fill:C.ink}}});
tx(s,`${input.scenarioCount}个场景`,907,169,280,66,24,C.pine,true);
tx(s,`${input.scenarioCount*2}次执行\n两策略配对\n记录可复算`,907,276,280,206,24);
tx(s,input.resultCaption??'结论限定于本次仿真场景与简化模型',72,607,1136,54,24,C.muted);
}
{
const s=slide('模型失效或缺参数时，明确记录原因','正式四十八次执行没有失败，但我们另做了边界例。突发侧风达到每秒六米，超过每秒五米的固定空速模型，执行器在零点五秒记录失败。缺少参考曲线时，软件返回不可用，不生成预算。这些边界例单独保存，不混入正式场景分母。它们说明软件能记录信息不足与模型失效，真实飞行安全仍需独立验证。',sourcenotes('output/4C/evidence/boundaries/report.json','output/4C/evidence/boundaries/sudden_crosswind_failure.json','output/4C/evidence/boundaries/missing_reference.json'));
table(s,[['实际边界例','软件记录'],['突发6 m/s侧风','执行失败：轨迹保持模型失效'],['缺少参考曲线','参数不可用：不生成预算']],{h:284,widths:[455,681]});
tx(s,'边界例单独保存，未计入正式48次执行',72,523,1100,56,24,C.pine,true);
tx(s,'真实飞行安全仍待独立验证',72,602,1100,52,24,C.muted);
}
{
const s=slide('返航与变化进入同一决策流程','路线搜索采用已有的A星算法。作品的特色是把任务中需要考虑的四件事接在一起。第一，顺风和逆风让同一路段的去程与返程代价不同。第二，每次去下一点，都独立核算回到起点的路线。第三，风场或障碍改变以后，按当前观测重新判断。第四，保留参数、轨迹、事件与决策理由。两种规划遵守相同预算和信息条件，其他人可以复查差异来自哪里。',input.sources.software);
table(s,[['实现特点','对任务预演的作用'],['考虑风向','同一路段的去程与返程代价可不同'],['独算返程','每次去下一点，都核算回收路线'],['条件变化后重算','风场或障碍改变，重新判断'],['保留运行档案','保存参数、轨迹与决策理由']],{h:392,widths:[360,776]});
tx(s,'A*为基础方法，本作贡献是任务流程与证据组织',72,602,1100,55,24,C.muted);
}
{
const s=slide('软件已完成，学生实作待补足','当前已完成本机软件首版、厂家曲线提取、正式仿真与边界记录，以及材料。编程和材料制作使用智能工具辅助。两名学生还需要真实完成需求核对、代码理解、同学试用和真人演练，并登记自己的贡献。现有结果限于声明的仿真模型，真实低温电池与现场飞行尚待独立验证。','智能工具辅助编程与材料。学生需求核对、理解、试用和真人演练尚待真实完成。现有仿真结果不构成真实飞行验证。');
table(s,[['状态','内容'],['已完成','本机首版、参数提取、仿真与边界记录'],['工具辅助','编程、实验整理与材料制作'],['学生待做','需求核对、代码理解、试用与真人演练']],{h:368,widths:[283,853]});
tx(s,'真实低温电池与现场飞行尚待独立验证',72,598,1100,55,24,C.muted);
}
{
const s=slide('交付与下一步','本作交付的是可以本机运行、比较两种规划、回放轨迹并导出档案的软件。它把输入条件、决策记录和仿真结果放进同一流程。下一步由学生核对真实需求、团队身份和下一届参赛规则，再逐项补足独立低温数据与真实飞行验证。谢谢各位评委。',sourcenotes(policySource,input.sources.software));
tx(s,'本机任务预演软件',72,190,1136,80,32,C.pine,true);
tx(s,'距离与能量两种规划\n二维轨迹回放\n结果与记录导出',72,313,1100,194,24);
tx(s,'待核对：景区需求、团队身份与下一届规则',72,577,1136,61,24,C.muted);
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
tx(s,'正式48次：0失败，4次部分任务后返航',72,471,1100,50,20,C.pine,true);
tx(s,'另存4个边界例：失败、缺曲线、温度不覆盖、首点阻塞',72,551,1110,88,20,C.muted);
}
{
const s=slide('V3证据的适用范围','答辩参考。V3发布清单明确记录研究状态为选型后候选，尚待独立确认。原晋级门槛没有通过，项目验收没有通过，真实数据验证和在线部署切换也没有发生。本次用冻结运行时成功执行原示例请求，十秒预测耗电约零点零四零九六安时，历史基线约零点零三七零八安时。请求没有未来标签，所以没有计算准确率。真实调用证实代码可以执行，独立准确度确认仍待新数据。',sourcenotes('learn/Phase4/releases/energy_residual_lstm_v3_rc1/manifest.json','learn/Phase4/releases/energy_residual_lstm_v3_rc1/MODEL_DECISION.md','output/4C/evidence/lstm_actual_response.json'),true);
table(s,[['证据','当前状态'],['标签来源','AIRSIM_FORMULA_BATTERY'],['模型选型','查看候选结果后的探索性选择'],['独立最终确认','待完成'],['真实低温与真实飞行','尚未验证'],['在线模型切换','未发生']],{h:360,widths:[386,750],pt:20});
tx(s,'本次真实调用：10秒预测0.04096 Ah，历史基线0.03708 Ah',72,554,1110,44,20,C.pine,true);
tx(s,'无未来标签，不计算准确率',72,612,1110,44,20,C.muted);
}
{
const s=slide('复现与贡献说明','答辩参考。交付包提供软件源码、已构建网页、启动脚本、曲线来源与提取记录，以及正式和边界实验档案。按README在本机启动后，用同一参数可以复查记录与复演。编程、实验整理与材料制作使用智能工具辅助，学生的需求核对、理解、同学试用和现场真人演练须真实完成后登记。一万元分配为预算上限，详见预算文档，未填写未发生的支出。',sourcenotes('learn/competition/README.md','learn/competition/BUDGET.md','learn/competition/STUDENT_TASKS.md','智能工具辅助编程与材料，学生真实贡献按完成记录填写。'),true);
table(s,[['交付内容','复现入口'],['本机软件与已构建网页','README与本机启动脚本'],['参数与曲线提取记录','p42a_reference.json与源PDF'],['正式和边界仿真档案','evidence目录'],['学生任务与预算','STUDENT_TASKS.md与BUDGET.md']],{h:392,widths:[517,619],pt:20});
tx(s,'智能工具辅助实现，学生实际理解与演练待完成',72,602,1110,57,20,C.muted);
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
