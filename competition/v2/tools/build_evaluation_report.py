"""Build an offline, plain-language result page and traceable Matplotlib figures."""
import argparse
import csv
import gzip
import json
from pathlib import Path
import shutil

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties, fontManager

from competition.v2.tools.evaluate import METHODS
from competition.v2.tools.prepare_day2 import write_json

NAMES={'fixed_order':'按清单走','nearest_feasible':'就近安排','value_per_cost':'逐点算划算','subset_dp':'统筹安排'}
COLORS=['#a4b5aa','#7c9687','#527967','#1c674f']


def compact(row):
    if row['execution']!='FINISHED':raise ValueError('report_template_requires_review_of_execution_errors')
    return {k:row[k] for k in ('case_id','condition_id','topology','temperature_c','kind','error_profile','selector_id',
                              'budget_mode','execution','normalized_value','archive','result_sha256')} | row['summary']


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--font',required=True,type=Path);args=p.parse_args();out=args.output.resolve()
    report=json.loads((out/'report.json').read_text())
    if not report['passed']:raise ValueError('audit_not_passed')
    rows=json.loads((out/'results.json').read_text())['records'];analysis=json.loads((out/'analysis.json').read_text())
    data={'freeze_sha256':report['freeze_sha256'],'rows':[compact(r) for r in rows],'counterexample':[]}
    pair=next(r for r in analysis['method_pairs'] if r['budget_mode']=='bounded' and r['second']=='nearest_feasible')
    ids=pair['case_ids']['losses'][0]
    for case_id in reversed(ids):
        row=next(r for r in rows if r['case_id']==case_id)
        # This narrative is deliberately tied to this frozen version.
        if (row['topology'],row['temperature_c'],row['kind'],row['error_profile'])!=('open',0.,'low_budget','joint_outside_declared'):
            raise ValueError('counterexample_narrative_requires_revision')
        archive=json.loads(gzip.decompress((out/row['archive']).read_bytes()))
        scene=archive['configuration']['scenario']
        data['counterexample'].append(compact(row)|{'grid':scene['grid'],'base':scene['base'],
            'tasks':scene['tasks'],'path':archive['state']['executed_path']})
    assets=out/'assets';assets.mkdir(exist_ok=True);shutil.copy2(args.font,assets/'SourceHanSansSC-Regular.otf')
    template=Path(__file__).resolve().parents[1]/'presentation/results.template.html'
    encoded=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('<','\\u003c')
    (out/'看懂测试结果.html').write_text(template.read_text().replace('__REPORT_DATA__',encoded),encoding='utf-8')
    fontManager.addfont(str(args.font));font=FontProperties(fname=str(args.font))
    plt.rcParams.update({'font.family':font.get_name(),'axes.unicode_minus':False,'font.size':14,
        'axes.spines.top':False,'axes.spines.right':False,'axes.spines.left':False,
        'axes.spines.bottom':False,'axes.labelcolor':'#20352e','text.color':'#20352e',
        'xtick.color':'#53685e','ytick.color':'#20352e','svg.fonttype':'none'})
    charts=out/'charts';charts.mkdir(exist_ok=True);chart_rows=[]
    def save(fig,name):
        fig.savefig(charts/(name+'.png'),dpi=150,facecolor='white',bbox_inches='tight')
        fig.savefig(charts/(name+'.svg'),facecolor='white',bbox_inches='tight');plt.close(fig)
    selected=[r for r in analysis['table'] if r['budget_mode']=='bounded']
    fig,ax=plt.subplots(figsize=(11,5.8));fig.subplots_adjust(left=.18,bottom=.22,top=.8,right=.94)
    scores=[r['mean_normalized_value']*100 for r in selected]
    ax.barh(range(4),scores,color=COLORS,height=.55);ax.invert_yaxis();ax.set_yticks(range(4),[NAMES[r['selector_id']] for r in selected]);ax.set_xlim(0,100)
    ax.set_xticks([0,25,50,75,100]);ax.grid(axis='x',alpha=.15);ax.set_axisbelow(True)
    for i,score in enumerate(scores):ax.text(score+1.4,i,f'{score:.1f} 分',va='center',fontsize=16)
    fig.suptitle('同样 144 组条件，统筹安排的平均完成分较高',x=.06,y=.98,ha='left',fontsize=21)
    ax.set_xlabel('达标后的完成分（满分 100）',labelpad=12)
    fig.text(.06,.05,'固定计入误差余量；包含全部三种误差设置。未返回或未留足储备记 0 分。\n合成软件条件的描述性结果，不代表真实飞行成功概率。',fontsize=11,color='#53685e')
    for r in selected:chart_rows.append({'chart':'methods_bounded','group':r['selector_id'],'mode':'bounded','value':r['mean_normalized_value']*100,'n':r['n'],'source':'analysis.json/table'})
    save(fig,'01_四种安排的完成分')
    profiles=['no_added_bias','joint_within_declared','joint_outside_declared'];profile_names=['无额外偏差','偏差在设置范围内','偏差超出设置范围']
    fig,ax=plt.subplots(figsize=(11,6));fig.subplots_adjust(left=.1,bottom=.22,top=.78,right=.95)
    for offset,mode,label,color in [(-.18,'nominal','直接使用估算','#a4b5aa'),(.18,'bounded','计入误差余量','#1c674f')]:
        values=[]
        for profile in profiles:
            r=next(r for r in analysis['strata'] if r['dimension']=='error_profile' and r['level']==profile and r['selector_id']=='subset_dp' and r['budget_mode']==mode)
            values.append(r['returned_with_reserve']);chart_rows.append({'chart':'budget_return','group':profile,'mode':mode,'value':values[-1],'n':r['n'],'source':'analysis.json/strata'})
        bars=ax.bar([i+offset for i in range(3)],values,width=.32,label=label,color=color)
        ax.bar_label(bars,labels=[f'{n} / 48' for n in values],padding=5,fontsize=13)
    ax.set_ylim(0,56);ax.set_yticks([0,12,24,36,48]);ax.set_ylabel('回来且留够预设电量的执行数');ax.set_xticks(range(3),profile_names);ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True)
    ax.legend(loc='upper center',bbox_to_anchor=(.5,1.19),ncol=2,frameon=False)
    fig.suptitle('给估算留余量，有帮助，也有边界',x=.06,y=.98,ha='left',fontsize=21)
    fig.text(.06,.05,'同为统筹安排；每种误差设置 48 组固定条件，未起飞也保留在分母中。\n10% 余量是设计参数，不是经实测校准的置信区间或安全保证。',fontsize=11,color='#53685e')
    save(fig,'02_预算余量的作用与边界')
    fig,ax=plt.subplots(figsize=(11,6));fig.subplots_adjust(left=.1,bottom=.22,top=.78,right=.95)
    for method,color,marker in zip(METHODS,COLORS,['s','^','D','o']):
        temps=[0.,-10.,-20.];values=[]
        for temp in temps:
            r=next(r for r in analysis['strata'] if r['dimension']=='temperature_c' and r['level']==temp and r['selector_id']==method and r['budget_mode']=='bounded')
            values.append(r['mean_normalized_value']*100);chart_rows.append({'chart':'temperature','group':f'{method}:{temp}','mode':'bounded','value':values[-1],'n':r['n'],'source':'analysis.json/strata'})
        ax.plot(range(3),values,label=NAMES[method],color=color,marker=marker,linewidth=2.5,markersize=8)
    ax.set_ylim(0,100);ax.set_ylabel('平均达标完成分');ax.set_xticks(range(3),['0℃','−10℃','−20℃']);ax.grid(axis='y',alpha=.15)
    ax.legend(loc='upper center',bbox_to_anchor=(.5,1.2),ncol=4,frameon=False,fontsize=12)
    fig.suptitle('更冷时，任务预算收紧',x=.06,y=.98,ha='left',fontsize=21)
    fig.text(.06,.05,'固定计入误差余量；每种方法每个温度 48 组，包含全部情境与误差设置。\n采用指定电芯参考条件下的简化模型；不是景区实测温度与续航关系。',fontsize=11,color='#53685e')
    save(fig,'03_三个温度的任务完成分')
    with (charts/'图表数据.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=chart_rows[0].keys());writer.writeheader();writer.writerows(chart_rows)
    write_json(out/'presentation-data.json',data)
    print(json.dumps({'report':'看懂测试结果.html','figures':3,'counterexample_case_ids':ids,'font':font.get_name()},ensure_ascii=False))


if __name__=='__main__':main()
