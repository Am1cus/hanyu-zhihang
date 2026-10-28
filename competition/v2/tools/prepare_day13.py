"""Export all declared development snapshots and an offline comparison page."""
from __future__ import annotations

import argparse
from datetime import date
import hashlib
import io
import json
from pathlib import Path
import platform
import unittest

from competition.v2.contracts import DecisionRequest, fingerprint
from competition.v2.planning_inputs import build_leg_table
from competition.v2.reference import REFERENCE_VERSION, brute_force_reference
from competition.v2.scenarios import development_scenarios, initial_request
from competition.v2.selectors import SELECTOR_VERSION, decide
from competition.v2.tools.prepare_day2 import write_json, verify_v1, source_audit

POLICIES = ('fixed_order', 'nearest_feasible', 'value_per_cost', 'subset_dp')
CASESET_VERSION = 'day13-current-snapshots-0.1'


def case_specs():
    """A fixed complete matrix, not a search for favorable display outcomes."""
    for scene in development_scenarios():
        for temperature in (0., -10., -20.):
            for soc in (.35, .55, .85):
                for mode in ('nominal', 'bounded'):
                    yield scene, temperature, soc, mode, 'matrix'
    scene = development_scenarios()[0]
    yield scene, -10., .1, 'bounded', 'low_budget'
    yield scene, -30., .55, 'bounded', 'missing_data'


def stable_record(record):
    return record.model_dump(mode='json', exclude={'computation_ms'})


def old_evidence_check(root):
    directory = root/'output/4C/v2/day11'
    audit = json.loads((directory/'delivery-audit.json').read_text())
    changed = [name for name, expected in audit['artifact_sha256'].items()
               if hashlib.sha256((directory/name).read_bytes()).hexdigest() != expected]
    return {'passed': not changed, 'changed_files': changed,
            'artifacts_checked': len(audit['artifact_sha256'])}


def build_cases():
    rows = []
    for index, (scene, temperature, soc, mode, kind) in enumerate(case_specs()):
        base = initial_request(scene, temperature_c=temperature, initial_soc=soc, budget_mode=mode)
        legs = build_leg_table(base)
        values = {task.id:task.value for task in base.task_catalog}
        records = {}
        for policy in POLICIES:
            request = DecisionRequest.model_validate({**base.model_dump(mode='json'), 'selector_id':policy})
            record = decide(request)
            repeat = decide(request)
            if stable_record(record) != stable_record(repeat):
                raise ValueError('nondeterministic_decision:'+policy)
            paths = []
            if record.action in {'CONTINUE','RETURN'}:
                previous = 'CURRENT'
                for target in (*record.ordered_task_ids,'BASE'):
                    leg = legs[previous,target]
                    blocked = set(base.observation.known_map.blocked)
                    if leg.status != 'PLANNED' or any(p in blocked for p in leg.path):
                        raise ValueError('invalid_displayed_plan_path')
                    if any(abs(a[0]-b[0])+abs(a[1]-b[1]) != 1 for a,b in zip(leg.path,leg.path[1:])):
                        raise ValueError('discontinuous_displayed_plan_path')
                    paths.append(leg.model_dump(mode='json'))
                    previous = target
            records[policy] = {'request':request.model_dump(mode='json'), 'record':record.model_dump(mode='json'),
                               'selected_value':sum(values[t] for t in record.ordered_task_ids),
                               'selected_count':len(record.ordered_task_ids), 'paths':paths,
                               'stable_decision_sha256':fingerprint(stable_record(record))}
        reference = brute_force_reference(base, legs)
        selected = records['subset_dp']
        budget = selected['record']['budget']
        if reference['status']=='FEASIBLE_PLAN':
            route_wh = sum(budget[key] for key in ('transit_wh','service_wh','return_wh'))
            matches = selected['selected_value']==reference['best_value'] and abs(route_wh-reference['route_wh'])<=1e-7
        else:
            matches = not selected['record']['ordered_task_ids'] and budget['status']!='SUFFICIENT'
        if not matches:
            raise ValueError('oracle_mismatch:'+str(index))
        rows.append({'id':f'case-{index+1:02d}', 'kind':kind, 'scenario_id':scene.id, 'label':scene.label,
                     'temperature_c':temperature,'remaining_ah_fraction':soc,'budget_mode':mode,
                     'base_request':base.model_dump(mode='json'),'decisions':records,
                     'reference':reference,'reference_match':matches,'execution_verified':False})
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--verified-on',type=date.fromisoformat,required=True)
    args=parser.parse_args()
    v2=Path(__file__).resolve().parents[1]
    learn=v2.parents[1]
    root=learn.parent
    out=args.output.resolve()
    for name in ('day1','day2','day11'):
        protected=root/'output/4C/v2'/name
        if out==protected or protected in out.parents: parser.error('historical_output_is_protected')
    out.mkdir(parents=True,exist_ok=True)
    cases=build_cases()
    payload={'version':CASESET_VERSION,'work_item_date':'2026-10-13','verified_on':args.verified_on.isoformat(),
             'selector_version':SELECTOR_VERSION,'reference_version':REFERENCE_VERSION,
             'scope':'precomputed_current_snapshot_plans_not_flight_execution',
             'interviews':'PAUSED_BY_USER','formal_executions':0,'cases':cases}
    write_json(out/'comparison-results.json',payload)
    template=(v2/'presentation/comparison.template.html').read_text()
    encoded=json.dumps(payload,ensure_ascii=False,allow_nan=False).replace('<','\\u003c')
    if template.count('__COMPARISON_DATA__')!=1: raise ValueError('template_data_slot_mismatch')
    (out/'方案对照.html').write_text(template.replace('__COMPARISON_DATA__',encoded),encoding='utf-8')
    stream=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(v2/'tests'),pattern='test_*.py',top_level_dir=str(learn))
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
    (out/'tests.txt').write_text(stream.getvalue(),encoding='utf-8')
    history=old_evidence_check(root)
    v1=verify_v1(root)
    sources=source_audit(learn)
    write_json(out/'previous-evidence.json',{'day11':history,'v1':v1})
    write_json(out/'parameter-audit.json',sources)
    matrix=[case for case in cases if case['kind']=='matrix']
    comparisons={}
    for policy in POLICIES[:-1]:
        diffs=[c['decisions']['subset_dp']['selected_value']-c['decisions'][policy]['selected_value'] for c in matrix]
        comparisons[policy]={'higher_value':sum(x>0 for x in diffs),'equal_value':sum(x==0 for x in diffs),
                             'lower_value':sum(x<0 for x in diffs),'conditions':len(diffs)}
    files=sorted(p for p in v2.rglob('*') if p.is_file() and p.suffix in {'.py','.md','.json','.html'})
    report={'verified_on':args.verified_on.isoformat(),'work_item_date':'2026-10-13',
            'scope':payload['scope'],'passed':result.wasSuccessful() and history['passed'] and v1['passed'] and sources['passed'],
            'tests':{'run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped)},
            'case_count':len(cases),'matrix_count':len(matrix),'decision_count':len(cases)*len(POLICIES),
            'reference_matches':sum(c['reference_match'] for c in cases),'deterministic_repeats':len(cases)*len(POLICIES),
            'planned_value_comparison_on_development_matrix':comparisons,
            'formal_v2_executions':0,'real_flights':0,'interviews':'PAUSED_BY_USER',
            'runtime':{'python':platform.python_version(),'platform':platform.platform(),'machine':platform.machine()},
            'computation_ms_scope':'wall_clock_including_leg_table_and_selection_not_flight_time',
            'maximum_decision_ms':max(r['record']['computation_ms'] for c in cases for r in c['decisions'].values()),
            'source_sha256':{str(p.relative_to(learn)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            'results_sha256':hashlib.sha256((out/'comparison-results.json').read_bytes()).hexdigest()}
    write_json(out/'report.json',report)
    print(json.dumps({key:report[key] for key in ('passed','tests','case_count','decision_count','reference_matches')},ensure_ascii=False))
    raise SystemExit(0 if report['passed'] else 1)


if __name__=='__main__':
    main()
