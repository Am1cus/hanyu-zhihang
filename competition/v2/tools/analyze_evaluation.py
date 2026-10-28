"""Audit frozen software executions and emit complete descriptive comparisons."""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import gzip
import hashlib
import json
from pathlib import Path
import statistics

from competition.v2.contracts import DecisionRequest, fingerprint
from competition.v2.reference import brute_force_reference
from competition.v2.runtime import RuntimeConfig, RuntimeRun
from competition.v2.scenarios import observed_grid
from competition.v2.tools.evaluate import load_frozen, sha, METHODS, MODES, PROFILES
from competition.v2.tools.prepare_day2 import write_json, source_audit, verify_v1


def paired(rows, first, second, field='selector_id'):
    key_fields=['condition_id','budget_mode'] if field=='selector_id' else ['condition_id','selector_id']
    groups={}
    for row in rows:groups.setdefault(tuple(row[k] for k in key_fields),{})[row[field]]=row
    diffs=[];ids={'wins':[],'ties':[],'losses':[]}
    for key,group in groups.items():
        if first not in group or second not in group:raise ValueError('missing_pair')
        a,b=group[first],group[second];delta=a['normalized_value']-b['normalized_value']
        category='wins' if delta>1e-12 else 'losses' if delta < -1e-12 else 'ties'
        ids[category].append([a['case_id'],b['case_id']]);diffs.append(delta)
    return {'first':first,'second':second,'n':len(diffs),
            **{k:len(v) for k,v in ids.items()},'mean_difference':statistics.fmean(diffs),
            'min_difference':min(diffs),'max_difference':max(diffs),'case_ids':ids}


def aggregate(rows):
    finished=[r for r in rows if r['execution']=='FINISHED']
    decision_times=[t for r in finished for t in r['decision_ms']]
    statuses=Counter(r['summary']['status'] if r['summary'] else r['execution'] for r in rows)
    return {'n':len(rows),'mean_normalized_value':statistics.fmean(r['normalized_value'] for r in rows),
        'mean_completed_count':statistics.fmean(r['summary']['completed_count'] if r['summary'] else 0 for r in rows),
        'statuses':dict(statuses),'returned_with_reserve':sum(r['summary']['returned'] and r['summary']['reserve_margin_wh']>=-1e-7 for r in finished),
        'returned_below_reserve':sum(r['summary']['returned'] and r['summary']['reserve_margin_wh']< -1e-7 for r in finished),
        'reserve_violation_wh_max':max((max(0.,-r['summary']['reserve_margin_wh']) for r in finished),default=0.),
        'decision_ms_median':statistics.median(decision_times) if decision_times else None,
        'decision_ms_max':max(decision_times,default=None),
        'interval_total':sum(r['complete_intervals'] for r in finished),
        'interval_covered':sum(r['covered_intervals'] for r in finished)}


def canonical_grid(grid):
    grid=dict(grid);grid['blocked']=sorted(grid['blocked']);grid['wind_regions']=sorted(grid['wind_regions'],key=lambda x:x['id'])
    return fingerprint(grid)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();frozen,specs=load_frozen(out)
    results=json.loads((out/'results.json').read_text());rows=results['records']
    if len(rows)!=len(specs) or {r['case_id'] for r in rows}!={s['case_id'] for s in specs}:raise ValueError('missing_result')
    by_id={r['case_id']:r for r in rows}
    replay_ids={s['case_id'] for s in sorted(specs,key=lambda s:hashlib.sha256(s['case_id'].encode()).hexdigest())[:24]}
    checks=[];replays=[];oracles=[]
    for index,spec in enumerate(specs):
        row=by_id[spec['case_id']]
        if row['configuration_sha256']!=spec['configuration_sha256']:raise ValueError('result_pair_mismatch')
        if row['execution']!='FINISHED':
            checks.append({'case_id':row['case_id'],'passed':False,'reason':row['execution']});continue
        path=out/row['archive']
        if sha(path)!=row['archive_sha256']:raise ValueError('archive_hash_mismatch')
        archive=json.loads(gzip.decompress(path.read_bytes()));config=RuntimeConfig.model_validate(archive['configuration'])
        if fingerprint(config)!=spec['configuration_sha256']:raise ValueError('archive_configuration_mismatch')
        if archive['summary']!=row['summary']:raise ValueError('archive_summary_mismatch')
        value=sum(t.value for t in config.scenario.tasks if t.id in archive['summary']['completed_ids'])
        effective=value if archive['summary']['returned'] and archive['summary']['reserve_margin_wh']>=-1e-7 else 0
        metric_matches=abs(row['normalized_value']-effective/sum(t.value for t in config.scenario.tasks))<1e-12
        wh=sum(t['average_voltage_v']*t['current_a']*t['dt_s']/3600 for t in archive['telemetry'])
        energy_error=abs(wh-archive['summary']['consumed_wh'])
        current_only=all(canonical_grid(d['request']['observation']['known_map'])==canonical_grid(observed_grid(config.scenario,d['t_s']).model_dump(mode='json')) for d in archive['decisions'])
        checks.append({'case_id':row['case_id'],'passed':row['checks']['passed'] and energy_error<=1e-7 and current_only and metric_matches,
                       'wh_error':energy_error,'current_observation_only':current_only,'metric_matches':metric_matches})
        if row['case_id'] in replay_ids:
            replay=RuntimeRun(config).run_all().export()
            replays.append({'case_id':row['case_id'],'matches':replay['result_sha256']==row['result_sha256'],
                            'original_sha256':row['result_sha256'],'replay_sha256':replay['result_sha256']})
        if row['selector_id']=='subset_dp' and row['budget_mode']=='nominal' and row['kind']=='normal' and row['error_profile']=='no_added_bias':
            first=archive['decisions'][0];request=DecisionRequest.model_validate(first['request'])
            ref=brute_force_reference(request);actual=first['record'];order=actual['ordered_task_ids']
            selected_value=sum(t.value for t in request.task_catalog if t.id in order)
            budget=actual['budget'];cost=sum(budget[k] for k in ('transit_wh','service_wh','return_wh'))
            gap=selected_value-(ref['best_value'] or 0)
            match=gap==0 and (ref['route_wh'] is None or abs(cost-ref['route_wh'])<=1e-7)
            oracles.append({'case_id':row['case_id'],'matches_value_and_cost':match,'value_gap':gap,
                            'actual_order':order,'actual_route_wh':cost,'reference':ref})
        if (index+1)%288==0:print(json.dumps({'audited':index+1,'of':len(specs)}),flush=True)
    write_json(out/'archive-audit.json',checks);write_json(out/'replays.json',replays);write_json(out/'static-reference.json',oracles)
    summary={'scope':'all_frozen_synthetic_conditions_descriptive_only','execution_count':len(rows),'map_count':4,
             'paired_conditions':144,'real_flights':0,'table':[], 'method_pairs':[], 'budget_pairs':[], 'strata':[], 'equal_task_energy':[]}
    stratified_pairs=[]
    for mode in MODES:
        selected=[r for r in rows if r['budget_mode']==mode]
        for method in METHODS:
            summary['table'].append({'budget_mode':mode,'selector_id':method,**aggregate([r for r in selected if r['selector_id']==method])})
        for baseline in METHODS[:-1]:summary['method_pairs'].append({'budget_mode':mode,**paired(selected,'subset_dp',baseline)})
        for dimension in ('temperature_c','kind','topology','error_profile'):
            for level in sorted({r[dimension] for r in selected},key=str):
                subset=[r for r in selected if r[dimension]==level]
                for baseline in METHODS[:-1]:
                    stratified_pairs.append({'budget_mode':mode,'dimension':dimension,'level':level,**paired(subset,'subset_dp',baseline)})
                for method in METHODS:
                    summary['strata'].append({'budget_mode':mode,'dimension':dimension,'level':level,'selector_id':method,**aggregate([r for r in subset if r['selector_id']==method])})
        for baseline in METHODS[:-1]:
            deltas=[];pairs=[]
            for condition in {r['condition_id'] for r in selected}:
                group={r['selector_id']:r for r in selected if r['condition_id']==condition}
                a,b=group['subset_dp'],group[baseline]
                if a['execution']!='FINISHED' or b['execution']!='FINISHED':continue
                x,y=a['summary'],b['summary']
                if x['returned'] and y['returned'] and min(x['reserve_margin_wh'],y['reserve_margin_wh'])>=-1e-7 and x['completed_ids'] and set(x['completed_ids'])==set(y['completed_ids']):
                    deltas.append(x['consumed_wh']-y['consumed_wh']);pairs.append([a['case_id'],b['case_id']])
            summary['equal_task_energy'].append({'budget_mode':mode,'baseline':baseline,'n':len(deltas),
                'mean_dp_minus_baseline_wh':statistics.fmean(deltas) if deltas else None,'case_ids':sorted(pairs),
                'scope':'same_completed_task_set_and_actual_return_reserve_constraints_only'})
    for method in METHODS:
        selected=[r for r in rows if r['selector_id']==method]
        for profile in (None,*PROFILES):
            subset=[r for r in selected if profile is None or r['error_profile']==profile]
            summary['budget_pairs'].append({'selector_id':method,'error_profile':profile or 'all',**paired(subset,'bounded','nominal','budget_mode')})
    root=out.parents[3];learn=root/'learn'
    previous=json.loads((out/'before/manifest.json').read_text())['prior_artifact_sha256']
    changed=[p for p,h in previous.items() if sha(root/p)!=h]
    sources=source_audit(learn);v1=verify_v1(root)
    report={'version':'competition-v2-evaluation-audit-0.1','verified_on':'2026-10-22',
        'passed':all(c['passed'] for c in checks) and len(replays)==24 and all(r['matches'] for r in replays)
          and len(oracles)==12 and all(r['matches_value_and_cost'] for r in oracles) and not changed and sources['passed'] and v1['passed'],
        'executions':len(rows),'execution_errors':sum(r['execution']!='FINISHED' for r in rows),
        'checks_passed':sum(c['passed'] for c in checks),'replays':len(replays),'replay_matches':sum(r['matches'] for r in replays),
        'static_references':len(oracles),'static_reference_matches':sum(r['matches_value_and_cost'] for r in oracles),
        'max_wh_error':max((c.get('wh_error',0.) for c in checks),default=0.),'prior_artifacts_unchanged':not changed,
        'prior_artifact_count':len(previous),'changed_prior_artifacts':changed,'parameter_audit':sources,'v1_audit':v1,
        'human_interviews':0,'human_tryout':'PENDING','real_flights':0,'freeze_sha256':frozen['freeze_sha256']}
    write_json(out/'report.json',report);write_json(out/'analysis.json',summary)
    write_json(out/'stratified-pairs.json',stratified_pairs)
    flat=[]
    for r in rows:
        s=r['summary'] or {}
        flat.append({k:r[k] for k in ('case_id','condition_id','topology','temperature_c','kind','error_profile','selector_id','budget_mode','execution','normalized_value')} |
                    {k:s.get(k) for k in ('status','completed_count','task_count','raw_value','effective_value','returned','reserve_margin_wh','consumed_wh','consumed_ah','t_s')} |
                    {'archive':r.get('archive'),'result_sha256':r.get('result_sha256')})
    with (out/'全部1152项结果.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(flat[0]));writer.writeheader();writer.writerows(flat)
    print(json.dumps({k:report[k] for k in ('passed','executions','execution_errors','checks_passed','replay_matches','static_reference_matches','max_wh_error','prior_artifacts_unchanged')},ensure_ascii=False))
    print(json.dumps(summary['table'],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
