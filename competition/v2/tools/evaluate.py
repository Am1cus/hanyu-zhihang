"""Freeze and execute the declared software comparison, retaining every outcome.

No selector is called during map generation or freezing. The only timed pilot
uses the two existing development maps. A held-out map is no longer unseen
after this batch; tuning would require a new version and new evaluation set.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import sys
from time import perf_counter

from competition.v2.contracts import fingerprint
from competition.v2.runtime import RuntimeConfig, RuntimeRun, execution_source_hashes
from competition.v2.scenarios import Scenario
from competition.v2.tools.prepare_day20 import validate_run
from competition.v2.tools.prepare_day2 import write_json

VERSION = 'competition-v2-evaluation-0.1'
METHODS = ('fixed_order', 'nearest_feasible', 'value_per_cost', 'subset_dp')
MODES = ('nominal', 'bounded')
PROFILES = ('no_added_bias', 'joint_within_declared', 'joint_outside_declared')
KINDS = ('normal', 'low_budget', 'gust', 'dynamic_obstacle')
TEMPERATURES = (0., -10., -20.)
LEARN = Path(__file__).resolve().parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def maps():
    """Fixed coordinates selected from topology, without evaluating outcomes."""
    definitions = [
        ('open', 16, 12, (1, 6), [],
         [(4,3),(3,9),(10,2),(13,8),(9,10)], [(7,6)]),
        ('detour_corridor', 18, 14, (1,7),
         [(7,y) for y in range(13) if y != 3] + [(12,y) for y in range(1,14) if y != 10],
         [(4,3),(3,11),(9,3),(15,2),(9,10),(15,10),(5,6),(16,6)], [(7,3)]),
        ('connected_zones', 16, 16, (2,8),
         [(7,y) for y in range(16) if y not in (4,11)] + [(x,7) for x in range(8,16) if x != 12],
         [(3,4),(4,12),(10,3),(13,5),(10,10),(13,13),(5,9),(14,9)], [(7,4)]),
        ('sparse_obstacles', 17, 13, (1,6),
         [(5,3),(5,4),(5,5),(8,8),(9,8),(10,8),(12,3),(12,4),(12,5),(6,10)],
         [(3,3),(4,9),(10,2),(14,6),(12,11)], [(8,6),(8,7)]),
    ]
    values = [1,3,5,3,5,3,1,5]
    labels = ['入口导览区','服务站外围','栈道观察点','冰雕展示区','游客返程通道','远端观景点','休息区外围','北侧补充观察点']
    result=[]
    for i,(topology,w,h,base,blocked,positions,closure) in enumerate(definitions,1):
        scene = Scenario.model_validate({
            'id':f'holdout-{topology.replace("_","-")}-{len(positions)}',
            'version':'v2-heldout-maps-0.1', 'split':'held_out',
            'label':f'新地图{i}：{topology}（合成，非景区测绘）',
            'provenance':'synthetic_software_map_not_a_real_park', 'need_validation':'PENDING',
            'grid':{'width':w,'height':h,'cell_size_m':80.,'blocked':blocked,
                    'blocked_cell_meaning':'fixed_altitude_2d_exclusion_area',
                    'wind_regions':[{'id':'east','x_min':w//2,'x_max':w-1,
                                     'y_min':0,'y_max':h-1,'vector':[-1.,0.]}]},
            'base':base, 'tasks':[{'id':chr(65+j),'label':labels[j],'position':pos,
                'value':values[j],'dwell_s':10.,'value_source':'synthetic_assumption_pending_need_check',
                'service_level':'optional_supplemental_observation','action_semantics':'simulated_dwell_only'}
                for j,pos in enumerate(positions)],
            'airspeed_ms':5.,'fixed_height_m':40.,'scheduled_events':[]})
        # Geometry-only reachability, independently of the planner or method.
        for exclusions in (set(scene.grid.blocked), set(scene.grid.blocked)|set(closure)):
            visited={base}; pending=[base]
            while pending:
                x,y=pending.pop()
                for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                    if scene.grid.contains(p) and p not in exclusions and p not in visited:
                        visited.add(p);pending.append(p)
            if any(p not in visited for p in positions):raise ValueError('map_not_connected')
        result.append({'topology':topology,'scenario':scene.model_dump(mode='json'),
                       'obstacle_cells':closure})
    return result


def specifications(map_rows):
    rows=[]
    for m,entry in enumerate(map_rows,1):
        for temp in TEMPERATURES:
            for kind in KINDS:
                for profile in PROFILES:
                    condition=f'M{m}-T{int(temp)}-{kind}-{profile}'
                    scene=json.loads(json.dumps(entry['scenario']))
                    if kind=='gust':
                        scene['scheduled_events']=[{'id':'east-gust','at_s':32.,'type':'wind',
                                                    'region_id':'east','vector':[-4.,0.]}]
                    elif kind=='dynamic_obstacle':
                        scene['scheduled_events']=[{'id':'closure','at_s':32.,'type':'obstacle',
                                                    'cells':entry['obstacle_cells']}]
                    for mode in MODES:
                        for method in METHODS:
                            config=RuntimeConfig(scenario=Scenario.model_validate(scene),temperature_c=temp,
                                initial_soc=.35 if kind=='low_budget' else .55,selector_id=method,
                                budget_mode=mode,error_profile=profile,seed=0)
                            rows.append({'case_id':f'C{len(rows)+1:04d}','condition_id':condition,
                                'map_id':scene['id'],'topology':entry['topology'],'temperature_c':temp,
                                'kind':kind,'error_profile':profile,'selector_id':method,'budget_mode':mode,
                                'configuration':config.model_dump(mode='json'),
                                'configuration_sha256':fingerprint(config)})
    validate_matrix(rows)
    return rows


def validate_matrix(rows):
    if len(rows)!=1152 or len({r['case_id'] for r in rows})!=1152:
        raise ValueError('matrix_count_or_duplicate_id')
    groups={}
    for row in rows:
        config=RuntimeConfig.model_validate(row['configuration'])
        if fingerprint(config)!=row['configuration_sha256']:raise ValueError('configuration_hash_mismatch')
        if any(row[k]!=getattr(config,k) for k in ('selector_id','budget_mode','temperature_c','error_profile')):
            raise ValueError('configuration_label_mismatch')
        groups.setdefault(row['condition_id'],[]).append(row)
    if len(groups)!=144:raise ValueError('condition_count')
    for group in groups.values():
        if {(r['selector_id'],r['budget_mode']) for r in group} != {(s,b) for s in METHODS for b in MODES} or len(group)!=8:
            raise ValueError('unpaired_condition')
        common=[]
        for row in group:
            config=dict(row['configuration']);config.pop('selector_id');config.pop('budget_mode')
            common.append(fingerprint(config))
        if len(set(common))!=1:raise ValueError('unequal_information_or_initial_state')


def freeze(out):
    if (out/'freeze.json').exists():raise ValueError('freeze_exists_do_not_overwrite')
    pilot_path=out/'pilot.json';pilot=json.loads(pilot_path.read_text())
    if len(pilot['runs'])!=12 or not all(r['checks']['passed'] for r in pilot['runs']):
        raise ValueError('development_pilot_not_passed')
    if {r['map'] for r in pilot['runs']} != {'dev-snowfield-5','dev-two-gates-8'}:
        raise ValueError('pilot_must_use_development_only')
    map_rows=maps();rows=specifications(map_rows)
    write_json(out/'maps.json',map_rows)
    (out/'configurations.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False,allow_nan=False)+'\n' for r in rows))
    timeout=max(30,math.ceil(20*max(r['wall_seconds'] for r in pilot['runs'])))
    source=execution_source_hashes()
    extras=['competition/v2/tools/evaluate.py','competition/v2/tools/prepare_day20.py',
            'competition/v2/tools/prepare_day2.py','competition/v2/reference.py','competition/data/p42a_reference.json']
    for name in extras:source[name]=sha(LEARN/name)
    for name in source:
        dest=out/'source-snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(LEARN/name,dest)
    # Full packages keep the snapshot independently executable, not just seven files.
    for folder in ('competition/core','competition/v2'):
        for p in (LEARN/folder).rglob('*'):
            if p.is_file() and p.suffix in {'.py','.json','.md','.html','.command'}:
                dest=out/'source-snapshot'/p.relative_to(LEARN);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dest)
    shutil.copy2(LEARN/'competition/__init__.py',out/'source-snapshot/competition/__init__.py')
    shutil.copy2(LEARN/'competition/v2/protocol.json',out/'protocol-at-freeze.json')
    manifest={'version':VERSION,'frozen_at_utc':datetime.now(timezone.utc).isoformat(),
        'externally_timestamped_preregistration':False,'scope':'deterministic_synthetic_conditions_not_real_flights',
        'plan_date':'2026-10-22','map_count':4,'condition_count':144,'execution_count':1152,
        'source_sha256':source,'file_sha256':{p.name:sha(p) for p in [out/'maps.json',out/'configurations.jsonl',pilot_path,out/'protocol-at-freeze.json']},
        'wall_timeout_seconds':timeout,'workers':4,'simulated_time_limit_s':10000,
        'seed_note':'fixed_geometry_and_events_no_random_sampling_seed_is_metadata',
        'normal_initial_ah_fraction':.55,'low_initial_ah_fraction':.35,
        'primary_metric':'effective_value / total_task_value; zero_unless_returned_and_reserve_met',
        'timeout_policy':'record_TIMEOUT_keep_logs_no_auto_retry_exclude_no_rows',
        'replay_selection':'first_24_case_ids_sorted_by_sha256_of_case_id',
        'static_reference_selection':'every_subset_dp_nominal_normal_no_added_bias_initial_request_12_cases',
        'change_rule':'no_outcome_tuning_after_freeze_keep_all_results_and_failures'}
    manifest['freeze_sha256']=fingerprint(manifest)
    write_json(out/'freeze.json',manifest)
    print(json.dumps({k:manifest[k] for k in ('execution_count','wall_timeout_seconds','freeze_sha256')}),flush=True)


def load_frozen(out, check_source=True):
    frozen=json.loads((out/'freeze.json').read_text());body=dict(frozen);claimed=body.pop('freeze_sha256')
    if fingerprint(body)!=claimed:raise ValueError('freeze_modified')
    for name,h in frozen['file_sha256'].items():
        if sha(out/name)!=h:raise ValueError('frozen_input_changed:'+name)
    if check_source:
        for name,h in frozen['source_sha256'].items():
            if sha(LEARN/name)!=h:raise ValueError('source_changed_since_freeze:'+name)
    rows=[json.loads(line) for line in (out/'configurations.jsonl').read_text().splitlines()]
    validate_matrix(rows)
    return frozen,rows


def worker(out, index):
    row=json.loads((out/'configurations.jsonl').read_text().splitlines()[index])
    start=perf_counter();run=RuntimeRun(RuntimeConfig.model_validate(row['configuration']),run_id=row['case_id']).run_all()
    check=validate_run(run);archive=run.export()
    archive['evaluation']={'version':VERSION,'case_id':row['case_id'],'validation':check}
    path=out/'runs'/f"{row['case_id']}.json.gz";path.parent.mkdir(parents=True,exist_ok=True)
    raw=json.dumps(archive,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()
    tmp=path.with_suffix('.tmp');tmp.write_bytes(gzip.compress(raw,mtime=0));tmp.replace(path)
    intervals=[r for r in run.intervals if not r['partial']]
    values=sum(t.value for t in run.scenario.tasks)
    record={k:v for k,v in row.items() if k!='configuration'}
    record.update(execution='FINISHED',summary=run.summary(),checks=check,
        normalized_value=run.summary()['effective_value']/values,total_task_value=values,
        archive=str(path.relative_to(out)),archive_sha256=sha(path),result_sha256=archive['result_sha256'],
        wall_seconds=perf_counter()-start,decision_ms=[d['record']['computation_ms'] for d in run.decisions],
        complete_intervals=len(intervals),covered_intervals=sum(r['covered'] for r in intervals),
        event_effects=run.response_metrics)
    write_json(out/'records'/f"{row['case_id']}.json",record)


def batch(out):
    frozen,rows=load_frozen(out)
    def one(index,row):
        path=out/'records'/f"{row['case_id']}.json"
        if path.exists():
            record=json.loads(path.read_text())
            if record['configuration_sha256']!=row['configuration_sha256']:raise ValueError('resume_configuration_mismatch')
            if record.get('archive') and sha(out/record['archive'])!=record['archive_sha256']:raise ValueError('resume_archive_changed')
            return record  # includes failures and timeouts; never retries them.
        start=perf_counter();log=out/'logs'/f"{row['case_id']}.txt";log.parent.mkdir(parents=True,exist_ok=True)
        status=None;code=None
        with log.open('w') as stream:
            try:
                result=subprocess.run([sys.executable,'-m','competition.v2.tools.evaluate','worker',
                    '--output',str(out),'--index',str(index)],cwd=LEARN,stdout=stream,stderr=stream,
                    timeout=frozen['wall_timeout_seconds'],check=False)
                code=result.returncode
                if code!=0:status='ERROR'
            except subprocess.TimeoutExpired:status='TIMEOUT'
        if status is None and path.exists():return json.loads(path.read_text())
        record={k:v for k,v in row.items() if k!='configuration'}
        record.update(execution=status or 'ERROR',exit_code=code,wall_seconds=perf_counter()-start,
                      log=str(log.relative_to(out)),normalized_value=0.,summary=None,
                      checks={'passed':False,'reason':'execution_did_not_produce_a_valid_archive'})
        write_json(path,record);return record
    start=perf_counter();done=0;errors=0
    with ThreadPoolExecutor(max_workers=frozen['workers']) as pool:
        futures={pool.submit(one,i,r):r['case_id'] for i,r in enumerate(rows)}
        for future in as_completed(futures):
            r=future.result();done+=1;errors+=r['execution']!='FINISHED'
            if done%96==0 or done==len(rows):print(json.dumps({'done':done,'total':len(rows),'execution_errors':errors,'seconds':round(perf_counter()-start,1)}),flush=True)
    records=[json.loads((out/'records'/f"{r['case_id']}.json").read_text()) for r in rows]
    write_json(out/'results.json',{'version':VERSION,'freeze_sha256':frozen['freeze_sha256'],
        'python':platform.python_version(),'platform':platform.platform(),'records':records})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['freeze','run','worker'])
    parser.add_argument('--output',required=True,type=Path);parser.add_argument('--index',type=int)
    args=parser.parse_args();out=args.output.resolve()
    if args.action=='freeze':freeze(out)
    elif args.action=='run':batch(out)
    else:worker(out,args.index)


if __name__=='__main__':main()
