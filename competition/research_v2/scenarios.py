"""Seeded synthetic geometry, generated without consulting planner outcomes."""
import random

from competition.v2.scenarios import Scenario

GENERATOR_VERSION='seeded-grid-20261113-0.1'
DEVELOPMENT_SEEDS=tuple(range(2026111300,2026111332))
CONFIRMATION_SEEDS=tuple(range(2026112300,2026112312))
KINDS=('normal','obstacle','wind_then_obstacle')


def generate(seed,index,split='development'):
    rng=random.Random(seed);base=(1,8);size=16
    cells=[(x,y) for x in range(size) for y in range(size) if (x,y)!=base]
    density=(0.,.1,.2)[index%3]
    blocked=set(rng.sample(cells,int(size*size*density)))
    reachable={base};pending=[base]
    while pending:
        x,y=pending.pop()
        for p in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0<=p[0]<size and 0<=p[1]<size and p not in blocked and p not in reachable:
                reachable.add(p);pending.append(p)
    count=5 if index%2==0 else 8
    if len(reachable)<count+1:raise ValueError('geometry_generator_insufficient_connected_cells')
    positions=rng.sample(sorted(reachable-{base}),count)
    tasks=[{'id':chr(65+i),'label':f'合成巡看点{i+1}','position':p,'value':rng.choice((1,3,5)),
            'dwell_s':float(rng.choice((0,10,20))),'value_source':'synthetic_assumption_pending_need_check',
            'service_level':'optional_supplemental_observation','action_semantics':'simulated_dwell_only'}
           for i,p in enumerate(positions)]
    scene=Scenario.model_validate({'id':f'random-{seed}','version':('v2-development-maps-0.3'
        if split=='development' else 'v2-heldout-maps-0.1'),'split':split,
        'label':f'随机合成地图 {seed}','provenance':'synthetic_software_map_not_a_real_park','need_validation':'PENDING',
        'grid':{'width':size,'height':size,'cell_size_m':80.,'blocked':sorted(blocked),
            'blocked_cell_meaning':'fixed_altitude_2d_exclusion_area','wind_regions':[{'id':'east',
                'x_min':8,'x_max':15,'y_min':0,'y_max':15,'vector':[-1.,0.]}]},
        'base':base,'tasks':tasks,'airspeed_ms':5.,'fixed_height_m':40.,'scheduled_events':[]})
    event_cells=sorted(reachable-{base,*positions})
    closure=rng.choice(event_cells)
    times=sorted(rng.sample((16.,32.,64.,80.),2))
    return {'seed':seed,'generator_version':GENERATOR_VERSION,'obstacle_density':density,
            'scenario':scene.model_dump(mode='json'),'closure_cell':list(closure),'event_times':times}


def with_events(entry,kind):
    scene=Scenario.model_validate(entry['scenario']);data=scene.model_dump(mode='json')
    first,second=entry['event_times']
    if kind=='normal':events=[]
    elif kind=='obstacle':events=[{'id':'closure','at_s':first,'type':'obstacle','cells':[entry['closure_cell']]}]
    elif kind=='wind_then_obstacle':events=[{'id':'gust','at_s':first,'type':'wind','region_id':'east','vector':[-4.,0.]},
        {'id':'closure','at_s':second,'type':'obstacle','cells':[entry['closure_cell']]}]
    elif kind=='blocked_return':
        x,y=scene.base
        events=[{'id':'base-isolated','at_s':32.,'type':'obstacle',
                 'cells':[(x-1,y),(x+1,y),(x,y-1),(x,y+1)]}]
    else:raise ValueError('unknown_research_event_kind')
    data['scheduled_events']=events
    return Scenario.model_validate(data)
