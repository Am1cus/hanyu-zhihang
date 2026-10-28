"""Verify the live demonstration and export all declared development runs."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
import platform
import unittest

from competition.v2.contracts import fingerprint
from competition.v2.runtime import RuntimeRun, RuntimeConfig, TERMINAL, preset_config
from competition.v2.tools.prepare_day2 import write_json, source_audit, verify_v1


def specifications():
    for preset in ('normal','obstacle','gust'):
        for selector in ('fixed_order','nearest_feasible','value_per_cost','subset_dp'):
            yield f'{preset}-{selector}',preset,{'selector_id':selector},False
    for profile in ('joint_within_declared','joint_outside_declared'):
        for mode in ('nominal','bounded'):
            yield f'{profile}-{mode}','normal',{'error_profile':profile,'budget_mode':mode,
                  'initial_soc':.55,'temperature_c':-10.},False
    for preset in ('low_budget','unavailable','blocked_return'):
        yield preset,preset,{'selector_id':'value_per_cost'},False
    yield 'manual-exclusion','normal',{'selector_id':'value_per_cost'},True


def validate_run(run):
    summary=run.summary()
    integrated=sum(t['average_voltage_v']*t['current_a']*t['dt_s']/3600 for t in run.telemetry)
    ah=sum(t['current_a']*t['dt_s']/3600 for t in run.telemetry)
    wh_error=abs(integrated-run.consumed_wh)
    ah_error=abs(ah-(run.q-run.initial_q))
    remaining_error=0. if run.initial_wh is None else abs(run.initial_wh-integrated-run.remaining_wh)
    collision_free=True
    for sample in run.telemetry:
        if sample['dt_s']==0 or sample['stage']=='DWELL':continue
        blocked={tuple(p) for p in run.scenario.grid.blocked}
        start=sample['t_s']-sample['dt_s']
        for event in run.events:
            if event['t_s']<=start+1e-8 and event['payload']['type']=='obstacle':
                blocked.update(map(tuple,event['payload']['cells']))
        a,b=sample['position_before'],sample['position']
        if math.dist(a,b)<1e-9:continue
        middle=[(a[i]+b[i])/2 for i in (0,1)]
        if abs(a[0]-b[0])<1e-8:
            edge={(round(middle[0]),math.floor(middle[1]+1e-8)),(round(middle[0]),math.ceil(middle[1]-1e-8))}
        elif abs(a[1]-b[1])<1e-8:
            edge={(math.floor(middle[0]+1e-8),round(middle[1])),(math.ceil(middle[0]-1e-8),round(middle[1]))}
        else:collision_free=False;break
        if edge&blocked:collision_free=False;break
    actual_return=(run.status in {'COMPLETED_RETURNED','PARTIAL_RETURNED'} and
                   run.distance_m>0 and math.dist(run.position,run.scenario.base)<1e-8)
    checks={'terminal':run.status in TERMINAL,'wh_integral':wh_error<=1e-7,'ah_integral':ah_error<=1e-7,
            'energy_conservation':remaining_error<=1e-7,'returned_matches_position_and_status':run.returned==actual_return,
            'no_duplicate_completed_tasks':len(run.completed)==len(set(run.completed)),
            'executed_edges_respect_observed_exclusions':collision_free,
            'no_future_queue_in_requests':all('scheduled_events' not in str(d['request']) for d in run.decisions)}
    return {'passed':all(checks.values()),'checks':checks,'wh_error':wh_error,'ah_error':ah_error,
            'energy_conservation_error':remaining_error}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--verified-on',type=date.fromisoformat,required=True)
    args=parser.parse_args()
    v2=Path(__file__).resolve().parents[1];learn=v2.parents[1];root=learn.parent;out=args.output.resolve()
    for name in ('day2','day11','day13'):
        protected=root/'output/4C/v2'/name
        if out==protected or protected in out.parents:parser.error('historical_output_is_protected')
    out.mkdir(parents=True,exist_ok=True)
    results=[]
    for index,(name,preset,options,manual) in enumerate(specifications(),1):
        run=RuntimeRun(preset_config(preset,**options),run_id=f'development-{index:02d}')
        if manual:
            run.advance(3.7);run.inject({'type':'obstacle','cells':[[8,3]]})
        run.run_all()
        archive=run.export()
        check=validate_run(run)
        replay=RuntimeRun(RuntimeConfig.model_validate(archive['configuration'])).run_all()
        check['replay_matches']=replay.export()['result_sha256']==archive['result_sha256']
        check['passed']=check['passed'] and check['replay_matches']
        write_json(out/'runs'/f'{index:02d}-{name}.json',archive)
        results.append({'case_id':name,'file':f'runs/{index:02d}-{name}.json','summary':run.summary(),
                        'checks':check,'event_effects':run.response_metrics,
                        'result_sha256':archive['result_sha256']})
    by_id={r['case_id']:r for r in results}
    normal=by_id['normal-value_per_cost']['summary']
    obstacle=by_id['obstacle-value_per_cost']['summary']
    gust=by_id['gust-value_per_cost']['summary']
    dynamic={'obstacle_changes_executed_distance':normal['distance_m']!=obstacle['distance_m'],
             'obstacle_changes_same_state_plan':any(m['plan_changed'] for m in by_id['obstacle-value_per_cost']['event_effects']),
             'gust_changes_duration_and_consumption':normal['t_s']!=gust['t_s'] and normal['consumed_wh']!=gust['consumed_wh']}
    write_json(out/'development-runs.json',{'scope':'all_declared_development_runs_not_formal_holdout',
        'verified_on':args.verified_on.isoformat(),'cases':results,'dynamic_checks':dynamic})
    stream=io.StringIO();suite=unittest.defaultTestLoader.discover(str(v2/'tests'),pattern='test_*.py',top_level_dir=str(learn))
    tests=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (out/'tests.txt').write_text(stream.getvalue())
    manifest=json.loads((root/'output/4C/v2/day20/before/manifest.json').read_text())
    changed=[name for name,h in manifest['day13_artifact_sha256'].items()
             if hashlib.sha256((root/'output/4C/v2/day13'/name).read_bytes()).hexdigest()!=h]
    sources=source_audit(learn);v1=verify_v1(root)
    write_json(out/'parameter-audit.json',sources)
    write_json(out/'previous-evidence.json',{'day13_unchanged':not changed,'changed_files':changed,'v1':v1})
    paths=sorted(p for p in v2.rglob('*') if p.is_file() and p.suffix in {'.py','.md','.json','.html','.command'})
    report={'work_period':'2026-10-20/2026-10-26','verified_on':args.verified_on.isoformat(),
        'passed':tests.wasSuccessful() and all(r['checks']['passed'] for r in results) and all(dynamic.values())
                 and not changed and v1['passed'] and sources['passed'],
        'scope':'reference_model_execution_development_acceptance_not_real_flight_or_formal_holdout',
        'tests':{'run':tests.testsRun,'failures':len(tests.failures),'errors':len(tests.errors),'skipped':len(tests.skipped)},
        'development_executions':len(results),'replays_matching':sum(r['checks']['replay_matches'] for r in results),
        'dynamic_checks':dynamic,'max_wh_integral_error':max(r['checks']['wh_error'] for r in results),
        'formal_holdout_executions':0,'real_flights':0,'interviews':'PAUSED_BY_USER',
        'python':platform.python_version(),'platform':platform.platform(),
        'source_sha256':{str(p.relative_to(learn)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
    write_json(out/'report.json',report)
    print(json.dumps({key:report[key] for key in ('passed','tests','development_executions','replays_matching','dynamic_checks')},ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':main()
