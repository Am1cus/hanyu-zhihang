"""Freeze, run and audit reserve sensitivity on the already-used October set.

This is a supplementary sensitivity analysis, NOT new unseen validation.
Report both the policy's own threshold and the same fixed 20% comparator.
Changing the passing threshold must not masquerade as better performance.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
from time import perf_counter

from competition.v2.contracts import fingerprint
from competition.v2.reserve_sensitivity import ReserveRun, SensitivityConfig, VERSION
from competition.v2.runtime import execution_source_hashes
from competition.v2.tools.evaluate import LEARN, load_frozen, sha
from competition.v2.tools.prepare_day20 import validate_run
from competition.v2.tools.prepare_day2 import write_json
from competition.v2.tools.analyze_evaluation import canonical_grid
from competition.v2.scenarios import observed_grid

FRACTIONS=(.1,.2,.3)


def freeze(out, baseline):
    if (out/'freeze.json').exists():raise ValueError('freeze_exists')
    original,specs=load_frozen(baseline)
    old_results=json.loads((baseline/'results.json').read_text())['records']
    if len(old_results)!=1152 or any(r['execution']!='FINISHED' for r in old_results):raise ValueError('baseline_incomplete')
    expected={r['case_id']:r['result_sha256'] for r in old_results}
    rows=[]
    for spec in specs:
        for fraction in FRACTIONS:
            parameters=SensitivityConfig(base_configuration=spec['configuration'],reserve_fraction=fraction)
            row={k:v for k,v in spec.items() if k not in ('configuration','configuration_sha256','case_id')}
            row.update(case_id=f"{spec['case_id']}-R{round(fraction*100):02d}",base_case_id=spec['case_id'],
                       reserve_fraction=fraction,configuration=parameters.model_dump(mode='json'),
                       configuration_sha256=fingerprint(parameters),baseline_result_sha256=expected[spec['case_id']])
            rows.append(row)
    out.mkdir(parents=True,exist_ok=True)
    (out/'configurations.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in rows))
    source=execution_source_hashes()
    extras=['competition/v2/reserve_sensitivity.py','competition/v2/tools/evaluate_reserve.py',
            'competition/v2/tools/evaluate.py','competition/v2/tools/analyze_evaluation.py',
            'competition/v2/tools/prepare_day20.py','competition/v2/tools/prepare_day2.py',
            'competition/data/p42a_reference.json']
    for name in extras:source[name]=sha(LEARN/name)
    for folder in ('competition/core','competition/v2','competition/data'):
        for p in (LEARN/folder).rglob('*'):
            if p.is_file() and p.suffix in {'.py','.json','.md','.html','.txt','.command'}:
                dest=out/'source-snapshot'/p.relative_to(LEARN);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    shutil.copy2(LEARN/'competition/__init__.py',out/'source-snapshot/competition/__init__.py')
    body={'version':VERSION,'frozen_at_utc':datetime.now(timezone.utc).isoformat(),'declared_on':'2026-10-27',
          'scope':'supplementary_sensitivity_on_used_synthetic_test_set_not_unseen_evaluation',
          'baseline_directory':str(baseline),'baseline_freeze_sha256':original['freeze_sha256'],
          'baseline_configurations_sha256':sha(baseline/'configurations.jsonl'),
          'baseline_results_sha256':sha(baseline/'results.json'),
          'baseline_artifact_sha256':{str(p.relative_to(baseline)):sha(p) for p in baseline.rglob('*') if p.is_file()},
          'fractions':list(FRACTIONS),'reserve_reference':'23C_full_reference_Wh',
          'fixed_comparison_fraction':.2,'base_executions':1152,'planned_executions':len(rows),
          'workers':4,'wall_timeout_seconds':30,'configuration_file_sha256':sha(out/'configurations.jsonl'),
          'source_sha256':source,'replay_rule':'first_24_case_ids_sorted_by_sha256_of_case_id',
          'no_auto_retry':True,'default_production_fraction_changed':False,
          'analysis':'all_conditions_stratified_paired_deltas_with_fixed_20_percent_comparator_no_p_values',
          'policy_choice':'no_optimal_real_aircraft_reserve_inference_no_outcome_tuning'}
    body['freeze_sha256']=fingerprint(body);write_json(out/'freeze.json',body)
    print(json.dumps({'planned_executions':len(rows),'freeze_sha256':body['freeze_sha256']}),flush=True)


def load(out):
    body=json.loads((out/'freeze.json').read_text());clean=dict(body);expected=clean.pop('freeze_sha256')
    if fingerprint(clean)!=expected:raise ValueError('freeze_changed')
    if sha(out/'configurations.jsonl')!=body['configuration_file_sha256']:raise ValueError('inputs_changed')
    for name,h in body['source_sha256'].items():
        if sha(LEARN/name)!=h:raise ValueError('source_changed:'+name)
    rows=[json.loads(line) for line in (out/'configurations.jsonl').read_text().splitlines()]
    if len(rows)!=3456 or len({r['case_id'] for r in rows})!=3456:raise ValueError('matrix_count')
    groups={}
    for row in rows:
        parameters=SensitivityConfig.model_validate(row['configuration'])
        if fingerprint(parameters)!=row['configuration_sha256']:raise ValueError('config_hash_mismatch')
        groups.setdefault(row['base_case_id'],[]).append(parameters)
    if len(groups)!=1152:raise ValueError('base_pair_count')
    for group in groups.values():
        if len(group)!=3 or {c.reserve_fraction for c in group}!=set(FRACTIONS) or len({fingerprint(c.base_configuration) for c in group})!=1:
            raise ValueError('unfair_reserve_pair')
    return body,rows


def metrics(run):
    summary=run.summary();total=sum(t.value for t in run.scenario.tasks)
    fixed_reserve=run.library.reference_wh*.2;fixed_margin=summary['remaining_wh']-fixed_reserve
    return {'raw_value_fraction':summary['raw_value']/total,
            'own_threshold_value_fraction':summary['effective_value']/total,
            'fixed_20_value_fraction':summary['raw_value']/total if summary['returned'] and fixed_margin>=-1e-7 else 0.,
            'fixed_20_margin_wh':fixed_margin,'fixed_20_pass':summary['returned'] and fixed_margin>=-1e-7,
            'own_threshold_pass':summary['returned'] and summary['reserve_margin_wh']>=-1e-7,
            'fixed_20_reserve_wh':fixed_reserve}


def worker(out,index):
    row=json.loads((out/'configurations.jsonl').read_text().splitlines()[index]);start=perf_counter()
    run=ReserveRun(SensitivityConfig.model_validate(row['configuration']),run_id=row['case_id']).run_all()
    check=validate_run(run);expected=run.library.reference_wh*row['reserve_fraction']
    check['all_decisions_use_declared_reserve']=all(d['request']['budget']['reserve_wh']==expected and d['record']['budget']['reserve_wh']==expected for d in run.decisions)
    check['current_observation_only']=all(canonical_grid(d['request']['observation']['known_map'])==canonical_grid(observed_grid(run.scenario,d['t_s']).model_dump(mode='json')) for d in run.decisions)
    check['passed']=check['passed'] and check['all_decisions_use_declared_reserve'] and check['current_observation_only']
    archive=run.export();path=out/'runs'/f"{row['case_id']}.json.gz";path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(archive,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode(),mtime=0))
    record={k:v for k,v in row.items() if k!='configuration'}
    record.update(execution='FINISHED',summary=run.summary(),metrics=metrics(run),checks=check,
                  result_sha256=archive['result_sha256'],archive=str(path.relative_to(out)),archive_sha256=sha(path),
                  baseline_matches=archive['result_sha256']==row['baseline_result_sha256'] if row['reserve_fraction']==.2 else None,
                  wall_seconds=perf_counter()-start)
    write_json(out/'records'/f"{row['case_id']}.json",record)


def batch(out):
    frozen,rows=load(out);start=perf_counter()
    def one(index,row):
        path=out/'records'/f"{row['case_id']}.json"
        if path.exists():
            record=json.loads(path.read_text())
            if record['configuration_sha256']!=row['configuration_sha256']:raise ValueError('resume_config_changed')
            if record.get('archive') and sha(out/record['archive'])!=record['archive_sha256']:raise ValueError('resume_archive_changed')
            return record
        log=out/'logs'/f"{row['case_id']}.txt";log.parent.mkdir(parents=True,exist_ok=True);error=None;code=None
        with log.open('w') as stream:
            try:
                result=subprocess.run([sys.executable,'-m','competition.v2.tools.evaluate_reserve','worker','--output',str(out),'--index',str(index)],cwd=LEARN,stdout=stream,stderr=stream,timeout=frozen['wall_timeout_seconds'])
                code=result.returncode
                if code:error='ERROR'
            except subprocess.TimeoutExpired:error='TIMEOUT'
        if error is None and path.exists():return json.loads(path.read_text())
        record={k:v for k,v in row.items() if k!='configuration'}
        record.update(execution=error or 'ERROR',exit_code=code,log=str(log.relative_to(out)),checks={'passed':False})
        write_json(path,record);return record
    done=errors=0
    with ThreadPoolExecutor(max_workers=frozen['workers']) as pool:
        futures=[pool.submit(one,i,row) for i,row in enumerate(rows)]
        for future in as_completed(futures):
            record=future.result();done+=1;errors+=record['execution']!='FINISHED'
            if done%288==0 or done==len(rows):print(json.dumps({'done':done,'total':len(rows),'process_errors':errors,'seconds':round(perf_counter()-start,1)}),flush=True)
    records=[json.loads((out/'records'/f"{row['case_id']}.json").read_text()) for row in rows]
    write_json(out/'results.json',{'freeze_sha256':frozen['freeze_sha256'],'records':records})


def aggregate(rows):
    done=[r for r in rows if r['execution']=='FINISHED'];n=len(rows)
    return {'n':n,'process_errors':n-len(done),'states':dict(Counter(r['summary']['status'] for r in done)),
            'mean_raw_value_fraction':sum(r['metrics']['raw_value_fraction'] for r in done)/n,
            'mean_own_threshold_value_fraction':sum(r['metrics']['own_threshold_value_fraction'] for r in done)/n,
            'mean_fixed_20_value_fraction':sum(r['metrics']['fixed_20_value_fraction'] for r in done)/n,
            'own_threshold_pass':sum(r['metrics']['own_threshold_pass'] for r in done),
            'fixed_20_pass':sum(r['metrics']['fixed_20_pass'] for r in done),
            'returned_below_own_threshold':sum(r['summary']['returned'] and r['summary']['reserve_margin_wh']< -1e-7 for r in done),
            'returned_below_fixed_20':sum(r['summary']['returned'] and r['metrics']['fixed_20_margin_wh']< -1e-7 for r in done),
            'mean_remaining_wh_all_outcomes':statistics.fmean(r['summary']['remaining_wh'] for r in done) if done else None}


def analyze(out):
    frozen,specs=load(out);rows=json.loads((out/'results.json').read_text())['records']
    by_id={r['case_id']:r for r in rows}
    if len(rows)!=len(specs) or set(by_id)!={r['case_id'] for r in specs}:raise ValueError('missing_results')
    replay_ids={r['case_id'] for r in sorted(specs,key=lambda s:hashlib.sha256(s['case_id'].encode()).hexdigest())[:24]}
    replays=[];checks=[]
    for spec in specs:
        r=by_id[spec['case_id']]
        if r['configuration_sha256']!=spec['configuration_sha256']:raise ValueError('result_config_mismatch')
        if r['execution']!='FINISHED':checks.append(False);continue
        if sha(out/r['archive'])!=r['archive_sha256']:raise ValueError('archive_corrupt')
        archive=json.loads(gzip.decompress((out/r['archive']).read_bytes()))
        if fingerprint(archive['configuration'])!=spec['configuration_sha256'] or archive['summary']!=r['summary']:raise ValueError('archive_disagrees')
        integrated=sum(t['average_voltage_v']*t['current_a']*t['dt_s']/3600 for t in archive['telemetry'])
        checks.append(r['checks']['passed'] and abs(integrated-r['summary']['consumed_wh'])<=1e-7)
        if r['case_id'] in replay_ids:
            replay=ReserveRun(SensitivityConfig.model_validate(archive['configuration'])).run_all()
            replays.append({'case_id':r['case_id'],'matches':replay.export()['result_sha256']==r['result_sha256']})
    summary={'overall':[],'strata':[],'paired_fixed_20':[]}
    for method in ('fixed_order','nearest_feasible','value_per_cost','subset_dp'):
        for mode in ('nominal','bounded'):
            selected=[r for r in rows if r['selector_id']==method and r['budget_mode']==mode]
            for fraction in FRACTIONS:
                group=[r for r in selected if r['reserve_fraction']==fraction]
                summary['overall'].append({'selector_id':method,'budget_mode':mode,'reserve_fraction':fraction,**aggregate(group)})
                for dimension in ('temperature_c','kind','error_profile','topology'):
                    for value in sorted({r[dimension] for r in group},key=str):
                        summary['strata'].append({'selector_id':method,'budget_mode':mode,'reserve_fraction':fraction,'dimension':dimension,'level':value,
                                                 **aggregate([r for r in group if r[dimension]==value])})
            groups={}
            for r in selected:groups.setdefault(r['base_case_id'],{})[r['reserve_fraction']]=r
            for fraction in (.1,.3):
                wins=ties=losses=0;deltas=[]
                for base_case,group in groups.items():
                    if set(group)!=set(FRACTIONS):raise ValueError('incomplete_paired_comparison')
                    if any(r['execution']!='FINISHED' for r in group.values()):continue
                    delta=group[fraction]['metrics']['fixed_20_value_fraction']-group[.2]['metrics']['fixed_20_value_fraction']
                    wins+=delta>1e-12;losses+=delta< -1e-12;ties+=abs(delta)<=1e-12;deltas.append(delta)
                summary['paired_fixed_20'].append({'selector_id':method,'budget_mode':mode,'reserve_fraction':fraction,'n':len(deltas),
                    'wins':wins,'ties':ties,'losses':losses,'mean_difference':statistics.fmean(deltas) if deltas else None})
    baseline=Path(frozen['baseline_directory'])
    changed=[name for name,h in frozen['baseline_artifact_sha256'].items() if sha(baseline/name)!=h]
    base_matches=[r.get('baseline_matches',False) for r in rows if r['reserve_fraction']==.2]
    report={'verified_on':'2026-10-27','scope':frozen['scope'],'executions':len(rows),'new_reserve_variants':2304,
            'twenty_percent_control_executions':len(base_matches),'baseline_matches':sum(base_matches),
            'archives_checked':len(checks),'archives_passed':sum(checks),'replays':len(replays),'replays_matching':sum(r['matches'] for r in replays),
            'process_errors':sum(r['execution']!='FINISHED' for r in rows),'original_artifacts_changed':changed,
            'real_flights':0,'production_default_changed':False,
            'passed':all(checks) and len(base_matches)==1152 and all(base_matches) and len(replays)==24 and all(r['matches'] for r in replays) and not changed}
    write_json(out/'analysis.json',summary);write_json(out/'report.json',report);write_json(out/'replays.json',replays)
    flat=[]
    for r in rows:
        if r['execution']!='FINISHED':flat.append({'case_id':r['case_id'],'execution':r['execution']});continue
        flat.append({k:r[k] for k in ('case_id','base_case_id','topology','temperature_c','kind','error_profile','selector_id','budget_mode','reserve_fraction','execution')}
                    |r['metrics']|{k:r['summary'][k] for k in ('status','returned','completed_count','raw_value','remaining_wh','reserve_wh','consumed_wh','consumed_ah')}|{'archive':r['archive']})
    fields=list(dict.fromkeys(k for row in flat for k in row))
    with (out/'全部储备比例结果.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader();writer.writerows(flat)
    print(json.dumps(report,ensure_ascii=False),flush=True)
    print(json.dumps([r for r in summary['overall'] if r['selector_id']=='subset_dp' and r['budget_mode']=='bounded'],ensure_ascii=False,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=['freeze','run','worker','analyze']);p.add_argument('--output',required=True,type=Path)
    p.add_argument('--baseline',type=Path);p.add_argument('--index',type=int);args=p.parse_args();out=args.output.resolve()
    if args.action=='freeze':freeze(out,args.baseline.resolve())
    elif args.action=='run':batch(out)
    elif args.action=='worker':worker(out,args.index)
    else:analyze(out)


if __name__=='__main__':main()
