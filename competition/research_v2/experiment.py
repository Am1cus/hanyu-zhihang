"""Freeze, execute once, and analyze the independently versioned power policy.

No outcomes are consulted by the geometry generator. Confirmation requires a
completed development run and freezes source before generating new geometry.
"""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import sys
import time

from competition.v2.contracts import fingerprint
from competition.v2.runtime import RuntimeConfig,RuntimeRun,execution_source_hashes
from competition.v2.tools.prepare_day20 import validate_run
from .adaptive import CandidateConfig,CandidateRun,VERSION
from .scenarios import DEVELOPMENT_SEEDS,CONFIRMATION_SEEDS,KINDS,generate,with_events

PROJECT=Path(__file__).resolve().parents[2]
POLICIES=('subset_dp','adaptive_subset_dp','value_per_cost')
TEMPERATURES=(0.,-10.,-20.)
SOCS=(.35,.55)
PROFILES=('no_added_bias','joint_within_declared','joint_outside_declared')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def source_files():
    names=set(execution_source_hashes())
    names.update(str(p.relative_to(PROJECT)) for p in Path(__file__).parent.glob('*.py'))
    names.update(('competition/v2/reference.py','competition/v2/tools/prepare_day20.py',
                  'competition/data/p42a_reference.json','competition/v2/requirements-lock.txt'))
    return {name:sha(PROJECT/name) for name in sorted(names)}


def freeze(out,phase,correctness,development=None):
    correctness=correctness.resolve()
    if not json.loads(correctness.read_text())['passed']:raise ValueError('correctness_gate_failed')
    if phase=='confirmation':
        if development is None:raise ValueError('development_report_required')
        prior=json.loads(development.read_text())
        if prior['phase']!='development' or not prior['execution_complete']:
            raise ValueError('development_execution_incomplete')
        prior_freeze=json.loads((development.parent/'freeze.json').read_text())
        if prior_freeze['protocol']['source_sha256']!=source_files():
            raise ValueError('source_changed_since_development')
    out.mkdir(parents=True,exist_ok=False)
    seeds=DEVELOPMENT_SEEDS[:4] if phase=='development' else CONFIRMATION_SEEDS
    protocol={'version':VERSION,'phase':phase,'frozen_at':datetime.now(timezone.utc).isoformat(),
        'seeds':list(seeds),'policies':POLICIES,'temperatures':TEMPERATURES,'initial_soc':SOCS,
        'profiles':PROFILES,'kinds':KINDS,'budget_mode':'bounded','reserve_fraction':.2,
        'candidate_rule':'max(original_power, completed_past_interval_Wh * 3600 / duration)',
        'source_sha256':source_files(),'correctness_report_sha256':sha(correctness),
        'development_report_sha256':sha(development) if development else None,
        'worker_timeout_s':30,'batch_timeout_s':3600,'workers':2,
        'promotion_rule':'candidate reserve failures and not-returned counts do not increase, at least one decreases; all-condition and normal-event mean effective scores do not decrease; complete valid executions required',
        'not_returned_definition':'includes refusal and worker errors; also report refusal and departed_not_returned separately',
        'analysis':'descriptive paired comparisons; synthetic maps, no population probability or significance claims',
        'python':sys.version,'platform':platform.platform()}
    # This lock is written BEFORE any confirmation geometry is generated.
    write(out/'protocol-lock.json',protocol)
    for name in protocol['source_sha256']:
        target=out/'source-snapshot'/name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(PROJECT/name,target)
    entries=[generate(seed,i,'development' if phase=='development' else 'held_out') for i,seed in enumerate(seeds)]
    write(out/'scenarios.json',entries)
    rows=[]
    for entry in entries:
        for temp in TEMPERATURES:
            for soc in SOCS:
                for profile in PROFILES:
                    for kind in KINDS:
                        condition=f"{entry['seed']}-{temp}-{soc}-{profile}-{kind}"
                        for policy in POLICIES:
                            config=RuntimeConfig(scenario=with_events(entry,kind),temperature_c=temp,
                                initial_soc=soc,error_profile=profile,budget_mode='bounded',seed=entry['seed'],
                                selector_id='subset_dp' if policy=='adaptive_subset_dp' else policy)
                            rows.append({'case_id':f'R{len(rows)+1:04d}','condition':condition,
                                'policy':policy,'kind':kind,'temperature_c':temp,'initial_soc':soc,'profile':profile,
                                'configuration':config.model_dump(mode='json'),'configuration_sha256':fingerprint(config)})
    (out/'configurations.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
    for folder in ('records','runs','logs'):(out/folder).mkdir()
    manifest={'protocol':protocol,'protocol_sha256':fingerprint(protocol),'cases':len(rows),
              'configurations_sha256':sha(out/'configurations.jsonl'),'scenarios_sha256':sha(out/'scenarios.json')}
    write(out/'freeze.json',manifest)
    print(json.dumps({'frozen':phase,'cases':len(rows),'directory':str(out)},ensure_ascii=False),flush=True)


def load(out):
    frozen=json.loads((out/'freeze.json').read_text())
    assert fingerprint(frozen['protocol'])==frozen['protocol_sha256'],'protocol changed'
    assert sha(out/'configurations.jsonl')==frozen['configurations_sha256'],'inputs changed'
    assert sha(out/'scenarios.json')==frozen['scenarios_sha256'],'maps changed'
    assert source_files()==frozen['protocol']['source_sha256'],'source changed after freezing'
    rows=[json.loads(line) for line in (out/'configurations.jsonl').read_text().splitlines()]
    assert len(rows)==frozen['cases']
    groups={}
    for row in rows:
        assert fingerprint(row['configuration'])==row['configuration_sha256']
        common=dict(row['configuration']);common.pop('selector_id')
        groups.setdefault(row['condition'],[]).append((row['policy'],fingerprint(common)))
    assert all(len(g)==3 and {p for p,_ in g}==set(POLICIES) and len({h for _,h in g})==1 for g in groups.values())
    return frozen,rows


def worker(out,index):
    _,rows=load(out);row=rows[index];started=time.perf_counter()
    target=out/'records'/(row['case_id']+'.json')
    if target.exists():raise ValueError('worker_result_exists_no_implicit_retry')
    config=RuntimeConfig.model_validate(row['configuration'])
    run=(CandidateRun(CandidateConfig(base_configuration=config)) if row['policy']=='adaptive_subset_dp'
         else RuntimeRun(config)).run_all()
    check=validate_run(run);archive=run.export()
    path=out/'runs'/(row['case_id']+'.json.gz')
    path.write_bytes(gzip.compress(json.dumps(archive,ensure_ascii=False,allow_nan=False).encode(),mtime=0))
    record={k:v for k,v in row.items() if k!='configuration'}
    record.update(process_status='ok' if check['passed'] else 'check_failed',checks=check,
        summary=run.summary(),task_total_value=sum(t.value for t in config.scenario.tasks),
        archive=str(path.relative_to(out)),archive_sha256=sha(path),result_sha256=archive['result_sha256'],
        decision_ms=[d['record']['computation_ms'] for d in run.decisions],wall_seconds=time.perf_counter()-started)
    write(target,record)
    if not check['passed']:raise ValueError('execution_invariant_failed')


def batch(out):
    frozen,rows=load(out)
    started_file=out/'RUN_STARTED.json'
    with started_file.open('x') as stream:json.dump({'started_at':datetime.now(timezone.utc).isoformat()},stream)
    deadline=time.monotonic()+3600;started=time.monotonic();completed=[]
    def one(index,row):
        remaining=deadline-time.monotonic();path=out/'records'/(row['case_id']+'.json')
        status=None
        if remaining<=0:status='batch_timeout_not_started'
        else:
            with (out/'logs'/(row['case_id']+'.log')).open('w') as log:
                try:
                    result=subprocess.run([sys.executable,'-m','competition.research_v2.experiment','worker',
                        '--output',str(out),'--index',str(index)],cwd=PROJECT,stdout=log,stderr=log,
                        timeout=min(30,remaining))
                    if result.returncode:status=f'exit_{result.returncode}'
                except subprocess.TimeoutExpired:status='timeout'
        if path.exists():
            record=json.loads(path.read_text())
            if status is not None:
                record['process_status']=status;write(path,record)
            return record
        record={k:v for k,v in row.items() if k!='configuration'}
        record.update(process_status=status or 'missing_result',summary=None,archive=None,decision_ms=[])
        write(path,record);return record
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(one,i,row) for i,row in enumerate(rows)]
        for future in as_completed(futures):
            completed.append(future.result())
            if len(completed)%25==0 or len(completed)==len(rows):
                progress={'completed':len(completed),'total':len(rows),'elapsed_s':time.monotonic()-started,
                    'process_statuses':dict(Counter(r['process_status'] for r in completed))}
                write(out/'progress.json',progress);print(json.dumps(progress),flush=True)
    analyze(out,frozen,sorted(completed,key=lambda row:row['case_id']),time.monotonic()-started)


def aggregate(rows):
    summaries=[r['summary'] for r in rows if r['process_status']=='ok']
    scores=[100*r['summary']['effective_value']/r['task_total_value'] if r['process_status']=='ok' else 0. for r in rows]
    times=sorted(t for r in rows for t in r['decision_ms'])
    return {'n':len(rows),'worker_errors':sum(r['process_status']!='ok' for r in rows),
        'reserve_shortfall_returned':sum(s['returned'] and s['reserve_margin_wh'] < -1e-7 for s in summaries),
        'not_returned':len(rows)-sum(s['returned'] for s in summaries),
        'refused':sum(s['status']=='REFUSED' for s in summaries),
        'departed_not_returned':sum(s['distance_m']>0 and not s['returned'] for s in summaries),
        'mean_effective_score':statistics.mean(scores),'mean_completed_count':sum(s['completed_count'] for s in summaries)/len(rows),
        'mean_consumed_wh_valid_runs':statistics.mean(s['consumed_wh'] for s in summaries) if summaries else None,
        'decision_ms_median':statistics.median(times) if times else None,
        'decision_ms_p95':times[min(len(times)-1,int(.95*len(times)))] if times else None,
        'statuses':dict(Counter(s['status'] for s in summaries))}


def analyze(out,frozen,rows,elapsed):
    by_policy={p:aggregate([r for r in rows if r['policy']==p]) for p in POLICIES}
    by_kind={kind:{p:aggregate([r for r in rows if r['policy']==p and r['kind']==kind]) for p in POLICIES} for kind in KINDS}
    baseline,candidate=by_policy['subset_dp'],by_policy['adaptive_subset_dp']
    complete=all(r['process_status']=='ok' for r in rows)
    gate={'complete_valid_executions':complete,
        'reserve_shortfall_not_increased':candidate['reserve_shortfall_returned']<=baseline['reserve_shortfall_returned'],
        'not_returned_not_increased':candidate['not_returned']<=baseline['not_returned'],
        'at_least_one_reliability_count_reduced':candidate['reserve_shortfall_returned']<baseline['reserve_shortfall_returned'] or candidate['not_returned']<baseline['not_returned'],
        'overall_score_not_decreased':candidate['mean_effective_score']>=baseline['mean_effective_score'],
        'normal_score_not_decreased':by_kind['normal']['adaptive_subset_dp']['mean_effective_score']>=by_kind['normal']['subset_dp']['mean_effective_score']}
    groups={}
    for row in rows:groups.setdefault(row['condition'],{})[row['policy']]=row
    pairs=Counter()
    for group in groups.values():
        a,b=group['adaptive_subset_dp'],group['subset_dp']
        if a['process_status']!='ok' or b['process_status']!='ok':pairs['invalid']+=1;continue
        difference=a['summary']['effective_value']-b['summary']['effective_value']
        pairs['better' if difference>0 else 'worse' if difference<0 else 'equal']+=1
    report={'phase':frozen['protocol']['phase'],'execution_complete':complete,'executions':len(rows),
        'conditions':len(groups),'elapsed_s':elapsed,'by_policy':by_policy,'by_kind':by_kind,
        'by_profile':{profile:{p:aggregate([r for r in rows if r['policy']==p and r['profile']==profile]) for p in POLICIES} for profile in PROFILES},
        'candidate_vs_original_pairs':dict(pairs),'gate':gate,'worth_further_validation':all(gate.values()),
        'default_algorithm_changed':False,'scope':'descriptive synthetic confirmation; not real flight validation',
        'freeze_sha256':sha(out/'freeze.json')}
    write(out/'results.json',rows);write(out/'report.json',report)
    print(json.dumps(report,ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('freeze','run','worker'))
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--phase',choices=('development','confirmation'))
    parser.add_argument('--correctness',type=Path);parser.add_argument('--development',type=Path);parser.add_argument('--index',type=int)
    args=parser.parse_args();out=args.output.resolve()
    if args.action=='freeze':freeze(out,args.phase,args.correctness,args.development)
    elif args.action=='run':batch(out)
    else:worker(out,args.index)


if __name__=='__main__':main()
