import fs from 'node:fs/promises';
import path from 'node:path';

const root=path.resolve(process.env.WORKSPACE_DIR??process.cwd());
const out=path.join(root,'output/4C/.build/presentation/deck-input.json');
const reference=JSON.parse(await fs.readFile(path.join(root,'learn/competition/data/p42a_reference.json'),'utf8'));
const report=JSON.parse(await fs.readFile(path.join(root,'output/4C/evidence/formal/report.json'),'utf8'));
const mean=values=>values.reduce((a,b)=>a+b,0)/values.length;
const labels={distance:'距离A*',energy:'能量A*'};
const metrics=['distance','energy'].map(strategy=>{
 const rows=report.cases.map(c=>c[strategy]);
 return{strategy,label:labels[strategy],avg_tasks:mean(rows.map(r=>r.visited_count)),completion_rate:mean(rows.map(r=>r.mission_completion_ratio)),return_rate:mean(rows.map(r=>Number(r.returned))),returned_count:rows.filter(r=>r.returned).length,full_task_count:rows.filter(r=>r.mission_completion_ratio===1).length,mean_wh:mean(rows.map(r=>r.total_energy_wh))};
});
const comparable=report.cases.filter(c=>c.comparison.status==='comparable');
const groups=[0,-10,-20].map(t=>({t,rows:comparable.filter(c=>c.temperature_c===t)})).filter(g=>g.rows.length);
const base=reference.curves.find(c=>c.temperature_c===23).cell_energy_wh;
const lowBudgetRun=JSON.parse(await fs.readFile(path.join(root,'output/4C/evidence/formal/runs/low_budget-s1-t-20-energy.json'),'utf8'));
const input={
 curveSummary:reference.curves.map(c=>({temperature_c:c.temperature_c,energy_wh:c.cell_energy_wh,k_ratio:c.cell_energy_wh/base})),
 voltageCurves:reference.curves,metrics,scenarioCount:report.aggregate.scenario_count,
 comparableChart:{categories:groups.map(g=>`${g.t}℃（${g.rows.length}对）`),distance_wh:groups.map(g=>mean(g.rows.map(r=>r.distance.total_energy_wh))),energy_wh:groups.map(g=>mean(g.rows.map(r=>r.energy.total_energy_wh)))},
 screenshots:Object.fromEntries(['map','budget','runtime','result','events'].map(name=>[name,`output/4C/.build/presentation/screens/${name}.png`])),
 screenshotProvenance:{map:'output/playwright/4C/preview-evaluated.png',budget:'output/playwright/4C/budget-minus20.png',runtime:'output/playwright/4C/manual-obstacle-reroute.png',result:'output/playwright/4C/archive-result.png',events:'output/playwright/4C/archive-events.png'},
 sources:{competition:'https://jsjds.blcu.edu.cn/gsjs1/jnjsq.htm',iceEconomy:'https://www.ndrc.gov.cn/xxgk/zcfb/ghwb/202412/P020241205581474196116.pdf',governmentReport:'https://www.npc.gov.cn/c2/c30834/202603/t20260316_453264.html',governmentReportVerifiedMirror:'https://www.moe.gov.cn/jyb_xwfb/xw_zt/moe_357/2026/2026_zt03/baogao/202603/t20260314_1430876.html',molicel:reference.source.url,software:'learn/competition/README.md；learn/competition/core/planning.py；learn/competition/core/simulator.py',experiment:'output/4C/evidence/formal/report.json；output/4C/evidence/formal/manifest.json；output/4C/evidence/formal/runs.csv',curveFile:'learn/competition/data/p42a_reference.json，原始PDF矢量提取，无模型拟合',demoExport:'.playwright-cli/mission-6d454f77-a255-4737-a791-455985436c2a.json'},
 decisionExample:[0,-20].map(temperature_c=>{const c=report.cases.find(c=>c.scenario_id==='low_budget-s1'&&c.temperature_c===temperature_c);if(!c||c.energy.initial_soc!==0.55)throw new Error('Actual low_budget-s1 result required');return{temperature_c,...c.energy};}),
 decisionBudget:lowBudgetRun.state.initial_whole_mission_budget,
 resultNarrative:`本次正式实验包括四类场景，每类两个固定场景，分别在零、负十和负二十摄氏度运行，共二十四个配对场景、四十八次执行。四十八次都返航，四十四次完成全部三个点，四次完成部分任务后返航。两种规划使用相同估算器、储备规则和观测，只改变路线目标。二十四对都完成相同非零工作量并满足返航储备，平均参考模型耗能差约百分之一点五九。共同返航不能归因为能量路线更安全，耗能差也不代表真实无人机节能。`,
 resultCaption:`48次返航，44次完整巡检。平均参考模型耗能差1.59%`,
 experimentDesign:'4类情景 × 2个固定场景 × 3个温度。储备为23℃参考能量的20%',
 aggregate:report.aggregate,
 fontFamily:'Source Han Sans SC'
};
await fs.mkdir(path.dirname(out),{recursive:true});await fs.writeFile(out,JSON.stringify(input,null,2));
console.log(JSON.stringify({inputPath:out,metrics,comparablePairs:comparable.length,chart:input.comparableChart}));
