"""New development geometry: independent selection, paths and execution checks."""
import argparse
from collections import Counter
import gzip
import json
from pathlib import Path
import time

from competition.v2.contracts import DecisionRequest, fingerprint
from competition.v2.planning_inputs import build_leg_table, assess_order
from competition.v2.reference import brute_force_reference
from competition.v2.runtime import RuntimeRun, RuntimeConfig, execution_source_hashes
from competition.v2.scenarios import initial_request
from competition.v2.selectors import decide
from competition.v2.tools.prepare_day20 import validate_run
from .path_reference import dijkstra_energy
from .scenarios import DEVELOPMENT_SEEDS, generate, with_events, KINDS


def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True,type=Path)
    out=parser.parse_args().output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'runs').mkdir()
    entries=[generate(seed,i) for i,seed in enumerate(DEVELOPMENT_SEEDS)]
    write(out/'scenarios.json',entries)
    write(out/'source.json',execution_source_hashes())
    static=[];dynamic=[];boundaries=[];started=time.monotonic()
    for i,entry in enumerate(entries):
        scene=with_events(entry,'normal')
        for mode in ('nominal','bounded'):
            request=initial_request(scene,temperature_c=-10.,initial_soc=.55,budget_mode=mode)
            legs=build_leg_table(request);decision=decide(request);reference=brute_force_reference(request,legs)
            value=sum(t.value for t in scene.tasks if t.id in decision.ordered_task_ids)
            assert reference['best_value']==value,(entry['seed'],mode,'value')
            route=sum((decision.budget.transit_wh,decision.budget.service_wh,decision.budget.return_wh))
            assert abs(route-reference['route_wh'])<=1e-7,(entry['seed'],mode,'energy')
            path_checks=0
            positions={'BASE':scene.base,'CURRENT':scene.base,**{t.id:t.position for t in scene.tasks}}
            for (a,b),leg in legs.items():
                oracle=dijkstra_energy(scene.grid,positions[a],positions[b],scene.airspeed_ms,request.model.estimated_power_w)
                assert (oracle is None)==(leg.status!='PLANNED')
                if oracle is not None:assert abs(oracle-leg.energy_wh)<=1e-7
                path_checks+=1
            static.append({'seed':entry['seed'],'mode':mode,'value':value,'route_wh':route,
                'reference_orders':reference['enumerated_orders'],'path_checks':path_checks,'passed':True})
            # Boundary arithmetic is checked with a fixed proposed order, not
            # with a different policy's optimum or changed physical execution.
            order=(scene.tasks[0].id,);budget=assess_order(request,legs,order)
            for margin in (-2e-7,0.,2e-7):
                data=request.model_dump(mode='json')
                data['observation']['available_wh_estimate']=(budget.assessed_demand_wh+margin)/(0.9 if mode=='bounded' else 1.)
                assessment=assess_order(DecisionRequest.model_validate(data),legs,order)
                assert (assessment.status=='SUFFICIENT')==(margin>=0)
                boundaries.append({'seed':entry['seed'],'mode':mode,'margin':margin,'passed':True})
        for kind in (*KINDS,'blocked_return','no_feasible','low_budget'):
            actual_kind=kind if kind not in ('no_feasible','low_budget') else 'normal'
            config=RuntimeConfig(scenario=with_events(entry,actual_kind),temperature_c=-10.,
                initial_soc=.1 if kind=='no_feasible' else .35 if kind=='low_budget' else .55,
                seed=entry['seed'])
            run=RuntimeRun(config)
            if actual_kind!='normal':
                baseline=RuntimeRun(config.model_copy(update={'scenario':scene}))
                assert run.decisions[0]['request']==baseline.decisions[0]['request']
            run.run_all();check=validate_run(run)
            archive=run.export();name=f'{i:02d}-{kind}.json.gz'
            (out/'runs'/name).write_bytes(gzip.compress(json.dumps(archive,ensure_ascii=False).encode(),mtime=0))
            assert check['passed'],(entry['seed'],kind,check)
            dynamic.append({'seed':entry['seed'],'kind':kind,'archive':'runs/'+name,
                            'summary':run.summary(),'checks':check})
        write(out/'progress.json',{'maps_completed':i+1,'elapsed_s':time.monotonic()-started})
        print(f'{i+1}/32 maps checked',flush=True)
    report={'passed':True,'scope':'synthetic development correctness, not independent candidate confirmation',
        'maps':32,'task_counts':dict(Counter(len(e['scenario']['tasks']) for e in entries)),
        'static_checks':static,'path_checks':sum(r['path_checks'] for r in static),'boundary_checks':boundaries,
        'dynamic_checks':dynamic,'statuses':dict(Counter(r['summary']['status'] for r in dynamic)),
        'elapsed_s':time.monotonic()-started,'source_sha256':execution_source_hashes()}
    write(out/'report.json',report)
    print(json.dumps({'passed':True,'maps':32,'static':len(static),'dynamic':len(dynamic)},ensure_ascii=False))


if __name__=='__main__':main()
