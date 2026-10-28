"""Deterministic reference-model execution, separate from current-only selection."""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
import uuid
from typing import Annotated, Literal

from pydantic import Field, StrictFloat, StrictInt

from competition.core.curves import CurveLibrary
from competition.core.planning import ground_speed
from .contracts import (BudgetMode, DecisionRequest, NonNegative, Record, Selector, fingerprint)
from .planning_inputs import build_leg_table
from .scenarios import Event, Scenario, WindEvent, ObstacleEvent, development_scenarios, initial_request
from .selectors import SELECTOR_VERSION, decide

RUNTIME_VERSION = 'competition-v2-runtime-0.1'
TERMINAL = {'COMPLETED_RETURNED','PARTIAL_RETURNED','REFUSED','FAILED','UNAVAILABLE','CANCELLED'}
STEP_S = .5


def execution_source_hashes():
    v2=Path(__file__).parent
    files=[v2/name for name in ('runtime.py','selectors.py','contracts.py','planning_inputs.py','scenarios.py')]
    files += [v2.parent/'core'/name for name in ('curves.py','planning.py')]
    return {str(p.relative_to(v2.parent.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}


class RuntimeConfig(Record):
    runtime_version: Literal['competition-v2-runtime-0.1'] = RUNTIME_VERSION
    scenario: Scenario
    temperature_c: StrictFloat = -10.
    initial_soc: Annotated[StrictFloat, Field(ge=0, le=1)] = .55
    selector_id: Selector = 'subset_dp'
    budget_mode: BudgetMode = 'bounded'
    error_profile: Literal['no_added_bias','joint_within_declared','joint_outside_declared'] = 'no_added_bias'
    speedup: Annotated[StrictFloat, Field(ge=1, le=100)] = 20.
    seed: Annotated[StrictInt, Field(ge=0)] = 0
    manual_events: tuple[Event, ...] = ()
    cancel_after_s: NonNegative | None = None


def preset_config(preset='normal', **options):
    """Public demonstrators are development inputs, not held-out evaluation."""
    if preset not in {'normal','obstacle','gust','low_budget','unavailable','blocked_return'}:
        raise ValueError('unknown_preset')
    scene=development_scenarios()[1].model_dump(mode='json')
    scene['scheduled_events']=[]
    options={'temperature_c':0.,'initial_soc':.85, **options}
    if preset=='obstacle':
        scene['scheduled_events']=[{'id':'north-closure','at_s':32.,'type':'obstacle','cells':[[8,3]]}]
    elif preset=='gust':
        scene['scheduled_events']=[{'id':'east-gust','at_s':32.,'type':'wind','region_id':'east','vector':[-4.,0.]}]
    elif preset=='blocked_return':
        # Predeclared extreme condition used to verify a real failure state.
        scene['scheduled_events']=[{'id':'track-hold-loss','at_s':180.,'type':'wind','region_id':'east','vector':[-8.,0.]}]
    elif preset=='low_budget': options['initial_soc']=.1
    elif preset=='unavailable': options['temperature_c']=-30.
    return RuntimeConfig(scenario=Scenario.model_validate(scene), **options)


class RuntimeRun:
    def __init__(self, config: RuntimeConfig, library=None, run_id=None):
        self.config=config
        self.library=library or CurveLibrary()
        self.id=run_id or str(uuid.uuid4())
        self.scenario=config.scenario
        self.speedup=config.speedup
        self.t_s=0.
        self._requested_s=0.
        self.node=self.scenario.base
        self.position=list(map(float,self.node))
        self.grid=self.scenario.grid.model_dump(mode='json')
        self.status='RUNNING'
        self.stage='PLANNING'
        self.ended_reason=None
        self.returned=False
        self.path=[]
        self.completed=[]
        self.target=None
        self.dwell_remaining_s=0.
        self.telemetry=[]
        self.decisions=[]
        self.events=[]
        self.response_metrics=[]
        self.executed_path=[self.position.copy()]
        self.intervals=[]
        self._interval=None
        self._pending=[]
        self._pending_grid=None
        self._source_hashes=execution_source_hashes()
        self._manual=list(config.manual_events)
        self._cancel_after=config.cancel_after_s
        self._queue=[(e.at_s,'scheduled',e) for e in self.scenario.scheduled_events]
        self._queue += [(e.at_s,'manual',e) for e in self._manual]
        self._queue.sort(key=lambda x:(x[0],x[1],x[2].id))
        self.q=self.initial_q=0.
        self.initial_wh=None
        self.consumed_wh=0.
        self.distance_m=0.
        self.reserve_wh=None
        try:
            self.template=initial_request(self.scenario,config.temperature_c,config.initial_soc,
                                          config.selector_id,config.budget_mode,config.error_profile,self.library)
            self.reserve_wh=self.template.budget.reserve_wh
            if self.template.observation.data_status!='AVAILABLE':
                self._end('UNAVAILABLE',self.template.observation.unavailable_reason)
                return
            self.curve=self.library.curve(config.temperature_c)
            self.q=self.initial_q=(1-config.initial_soc)*self.curve.capacity_ah
            self.initial_wh=self.curve.energy_between(self.q,self.curve.capacity_ah)
        except ValueError as exc:
            self._end('UNAVAILABLE',str(exc));return
        self._record(0.,self.q,self.position.copy(),0.)
        self._apply_due()
        if self.status=='RUNNING': self._choose('mission_started')
        if self._cancel_after==0 and self.status=='RUNNING': self._end('CANCELLED','operator_cancelled')

    @property
    def remaining_wh(self):
        return None if self.initial_wh is None else max(0.,self.initial_wh-self.consumed_wh)

    def current_request(self):
        if math.dist(self.position,self.node)>1e-8:
            raise ValueError('decision_requires_actual_grid_node')
        data=self.template.model_dump(mode='json')
        divisor={'no_added_bias':1.,'joint_within_declared':.9,'joint_outside_declared':.8}[self.config.error_profile]
        data['observation'].update(as_of_s=self.t_s,position=list(self.node),known_map=copy.deepcopy(self.grid),
            known_map_sha256=fingerprint(self.grid),available_wh_estimate=self.remaining_wh/divisor,
            completed_task_ids=self.completed.copy())
        return DecisionRequest.model_validate(data)

    def _choose(self, trigger):
        request=self.current_request()
        record=decide(request)
        legs=build_leg_table(request)
        planned=[]
        if record.action in {'CONTINUE','RETURN'}:
            previous='CURRENT'
            for target in (*record.ordered_task_ids,'BASE'):
                planned.append(legs[previous,target].model_dump(mode='json'))
                previous=target
        changed=budget_changed=False
        counterfactual=None
        if self._pending_grid is not None:
            # Compare at the SAME current node, charge and completion state.
            # Trimming a path already flown must not be called an event effect.
            previous=request.model_dump(mode='json')
            previous['observation'].update(known_map=copy.deepcopy(self._pending_grid),
                                           known_map_sha256=fingerprint(self._pending_grid))
            previous=DecisionRequest.model_validate(previous)
            baseline=decide(previous)
            old_legs=build_leg_table(previous)
            old_paths=[]
            if baseline.action in {'CONTINUE','RETURN'}:
                origin='CURRENT'
                for target in (*baseline.ordered_task_ids,'BASE'):
                    old_paths.append(old_legs[origin,target].model_dump(mode='json')['path']);origin=target
            changed=(baseline.action!=record.action or baseline.ordered_task_ids!=record.ordered_task_ids
                     or old_paths!=[p['path'] for p in planned])
            budget_changed=baseline.budget!=record.budget
            counterfactual={'scope':'same_current_state_with_map_before_joint_pending_events',
                            'request_sha256':fingerprint(previous),'record':baseline.model_dump(mode='json'),
                            'planned_paths':old_paths}
        row={'t_s':self.t_s,'trigger':trigger,'request':request.model_dump(mode='json'),
             'record':record.model_dump(mode='json'),'planned_legs':planned,'plan_changed':changed,
             'budget_changed':budget_changed,'responding_to':self._pending.copy()}
        self.decisions.append(row)
        for event_id in self._pending:
            event=next(e for e in self.events if e['event_id']==event_id)
            self.response_metrics.append({'event_id':event_id,'event_t_s':event['t_s'],'decision_t_s':self.t_s,
                'simulated_delay_s':self.t_s-event['t_s'],'decision_compute_ms':record.computation_ms,
                'plan_changed':changed,'budget_changed':budget_changed,'decision_index':len(self.decisions)-1,
                'same_state_counterfactual':counterfactual})
        self._pending=[]
        self._pending_grid=None
        if record.action=='STOP':
            self._end('UNAVAILABLE' if record.reason_code=='DATA_UNAVAILABLE' else 'FAILED',record.reason_code)
        elif record.action=='REFUSED':
            if self.distance_m>0: self._arrive_base()
            else: self._end('REFUSED',record.reason_code)
        else:
            self.target=record.ordered_task_ids[0] if record.ordered_task_ids else None
            self.path=[list(p) for p in planned[0]['path']]
            self.stage='OUTBOUND' if self.target else 'RETURN'
            if len(self.path)==1:
                if self.target: self._start_dwell()
                else: self._arrive_base()

    def _start_dwell(self):
        self.stage='DWELL'
        self.dwell_remaining_s=next(t.dwell_s for t in self.scenario.tasks if t.id==self.target)
        self.path=[list(self.node)]
        if self.dwell_remaining_s<=1e-9: self._finish_task()

    def _finish_task(self):
        self._finish_interval()
        if self.target in self.completed: raise ValueError('task_completed_twice')
        self.completed.append(self.target)
        self._choose('task_completed')

    def _arrive_base(self):
        if math.dist(self.position,self.scenario.base)>1e-8:
            raise ValueError('return_requires_actual_arrival')
        if self.distance_m<=1e-9:
            self._end('REFUSED','no_flight_executed');return
        self.returned=True
        status='COMPLETED_RETURNED' if len(self.completed)==len(self.scenario.tasks) else 'PARTIAL_RETURNED'
        self._end(status,'arrived_at_base')

    def _end(self,status,reason):
        self._finish_interval(partial=True)
        self.status,self.ended_reason,self.stage=status,reason,'TERMINAL'
        self.path=[]

    def _apply_due(self):
        while self._queue and self._queue[0][0]<=self.t_s+1e-9 and self.status=='RUNNING':
            _,source,event=self._queue.pop(0)
            event_id=f'{source}:{event.id}'
            if self._pending_grid is None: self._pending_grid=copy.deepcopy(self.grid)
            occupied={tuple(self.node)}
            if len(self.path)>1 and math.dist(self.position,self.node)>1e-8:
                occupied.add(tuple(self.path[1]))
            harmful=isinstance(event,ObstacleEvent) and bool(set(event.cells)&occupied)
            if isinstance(event,ObstacleEvent):
                blocked={tuple(p) for p in self.grid['blocked']}|set(event.cells)
                self.grid['blocked']=[list(p) for p in sorted(blocked)]
            else:
                for region in self.grid['wind_regions']:
                    if region['id']==event.region_id: region['vector']=list(event.vector)
            self.events.append({'event_id':event_id,'t_s':self.t_s,'source':source,
                'payload':event.model_dump(mode='json'),'applied':True,'intersects_occupied_edge':harmful})
            self._pending.append(event_id)
            if harmful: self._end('FAILED','occupied_edge_became_excluded')

    def inject(self,payload):
        """Queue a manual event at the next canonical step, making replay exact."""
        if self.status not in {'RUNNING','PAUSED'}: raise ValueError('terminal_run_rejects_event')
        at_s=(math.floor((self.t_s+1e-9)/STEP_S)+1)*STEP_S
        event_data={**payload,'id':f'manual-{len(self._manual)+1}','at_s':at_s}
        event=ObstacleEvent.model_validate(event_data) if payload.get('type')=='obstacle' else WindEvent.model_validate(event_data)
        if isinstance(event,ObstacleEvent):
            occupied={tuple(self.node),self.scenario.base}
            if len(self.path)>1: occupied.add(tuple(self.path[1]))
            if set(event.cells)&occupied: raise ValueError('cannot_exclude_occupied_edge_or_base')
            if len(set(event.cells))!=len(event.cells): raise ValueError('duplicate_exclusion_cells')
            if any(not self.scenario.grid.contains(p) for p in event.cells): raise ValueError('exclusion_outside_map')
        elif event.region_id not in {w.id for w in self.scenario.grid.wind_regions}:
            raise ValueError('unknown_wind_region')
        self._manual.append(event)
        self._queue.append((at_s,'manual',event))
        self._queue.sort(key=lambda x:(x[0],x[1],x[2].id))
        return {'event_id':'manual:'+event.id,'scheduled_at_s':at_s,'status':'QUEUED'}

    def control(self,action):
        if self.status in TERMINAL: raise ValueError('terminal_run_rejects_control')
        if action=='pause' and self.status=='RUNNING': self.status='PAUSED'
        elif action=='resume' and self.status=='PAUSED': self.status='RUNNING'
        elif action=='cancel':
            self._cancel_after=self.t_s
            self._end('CANCELLED','operator_cancelled')
        else: raise ValueError('invalid_control_for_state')

    def _begin_interval(self,kind,duration_s):
        if self._interval is None:
            estimate=duration_s*self.template.model.estimated_power_w/3600
            error=self.template.budget.cost_fraction_error
            self._interval={'kind':kind,'start_s':self.t_s,'start_position':self.position.copy(),
                'start_consumed_wh':self.consumed_wh,'estimated_wh':estimate,
                'lower_wh':max(0.,estimate*(1-error)),'upper_wh':estimate*(1+error),
                'interval_scope':'start_observation_estimate_unknown_future_events_not_used'}

    def _finish_interval(self,partial=False):
        if self._interval is not None:
            row=self._interval
            actual=self.consumed_wh-row.pop('start_consumed_wh')
            row.update(end_s=self.t_s,end_position=self.position.copy(),integrated_wh=actual,
                       partial=partial,covered=None if partial else row['lower_wh']-1e-7<=actual<=row['upper_wh']+1e-7)
            self.intervals.append(row);self._interval=None

    def _record(self,dt,previous_q,previous_position,speed):
        v0=self.curve.voltage(previous_q)*4
        v1=self.curve.voltage(self.q)*4
        self.telemetry.append({'t_s':self.t_s,'dt_s':dt,'position':self.position.copy(),
            'position_before':previous_position,'voltage_start_v':v0,'voltage_v':v1,'average_voltage_v':(v0+v1)/2,
            'current_a':self.library.current_a,'consumed_wh':self.consumed_wh,'remaining_wh':self.remaining_wh,
            'consumed_ah':self.q-self.initial_q,'groundspeed_ms':speed,'stage':self.stage,
            'known_map_sha256':fingerprint(self.grid)})

    def advance(self,duration_s):
        if isinstance(duration_s,bool) or not math.isfinite(duration_s) or duration_s<0:
            raise ValueError('invalid_advance_duration')
        if self.status!='RUNNING': return self
        self._requested_s+=duration_s
        while self.status=='RUNNING' and self.t_s<self._requested_s-1e-10:
            self._apply_due()
            if self.status!='RUNNING': break
            if self._pending and self.stage!='DWELL' and math.dist(self.position,self.node)<1e-8:
                self._choose('event_observed')
                if self.status!='RUNNING': break
            if self.t_s>=10000: self._end('FAILED','simulation_time_limit');break
            dt=min((math.floor((self.t_s+1e-9)/STEP_S)+1)*STEP_S-self.t_s,
                   self.curve.seconds_to_next_knot(self.q,self.library.current_a))
            if self._queue: dt=min(dt,max(0.,self._queue[0][0]-self.t_s))
            if self._cancel_after is not None and self._cancel_after>self.t_s+1e-9:
                dt=min(dt,self._cancel_after-self.t_s)
            moving=self.stage in {'OUTBOUND','RETURN'}
            speed=0.
            if moving:
                if len(self.path)<2: self._end('FAILED','missing_execution_path');break
                a,b=self.path[:2]
                if tuple(a) in {tuple(p) for p in self.grid['blocked']} or tuple(b) in {tuple(p) for p in self.grid['blocked']}:
                    self._end('FAILED','execution_edge_excluded');break
                speed=ground_speed(a,b,self.grid['wind_regions'],self.scenario.airspeed_ms)
                if speed is None: self._end('FAILED','wind_exceeds_track_hold_model');break
                left=math.dist(self.position,b)*self.scenario.grid.cell_size_m/speed
                interval_kind,interval_duration='edge',left
                dt=min(dt,left)
            elif self.stage=='DWELL':
                interval_kind,interval_duration='dwell',self.dwell_remaining_s
                dt=min(dt,self.dwell_remaining_s)
            else: self._end('FAILED','invalid_execution_stage');break
            if dt>self._requested_s-self.t_s+1e-9: break
            if dt<1e-10:
                self._end('FAILED','battery_curve_cutoff' if self.q>=self.curve.capacity_ah-1e-10 else 'zero_step');break
            self._begin_interval(interval_kind,interval_duration)
            old_q,old_pos=self.q,self.position.copy()
            self.q=min(self.curve.capacity_ah,self.q+self.library.current_a*dt/3600)
            self.consumed_wh+=self.curve.energy_between(old_q,self.q)
            self.t_s+=dt
            if moving:
                length=math.dist(self.position,b)
                distance=min(length,speed*dt/self.scenario.grid.cell_size_m)
                self.position=[self.position[i]+(b[i]-self.position[i])/length*distance for i in (0,1)]
                self.distance_m+=distance*self.scenario.grid.cell_size_m
            else: self.dwell_remaining_s=max(0.,self.dwell_remaining_s-dt)
            self._record(dt,old_q,old_pos,speed)
            self.executed_path.append(self.position.copy())
            self._apply_due()
            if self.status!='RUNNING': break
            if self.q>=self.curve.capacity_ah-1e-10:
                self._end('FAILED','battery_curve_cutoff');break
            if moving and math.dist(self.position,b)<1e-8:
                self.position=list(map(float,b));self.node=tuple(b);self.path=self.path[1:]
                self._finish_interval()
                if self.stage=='RETURN' and self.node==self.scenario.base: self._arrive_base()
                elif self._pending: self._choose('event_observed')
                elif self.stage=='OUTBOUND' and self.node==next(t.position for t in self.scenario.tasks if t.id==self.target): self._start_dwell()
            elif self.stage=='DWELL' and self.dwell_remaining_s<=1e-9: self._finish_task()
            if self.status=='RUNNING' and self._cancel_after is not None and self.t_s>=self._cancel_after-1e-9:
                self._end('CANCELLED','operator_cancelled')
        return self

    def run_all(self,max_seconds=10000.):
        if self.status=='PAUSED': raise ValueError('resume_before_run_all')
        self.advance(max(0.,max_seconds-self._requested_s))
        if self.status=='RUNNING': self._end('FAILED','evaluation_time_limit')
        return self

    def summary(self):
        value=sum(t.value for t in self.scenario.tasks if t.id in self.completed)
        margin=None if self.remaining_wh is None else self.remaining_wh-self.reserve_wh
        return {'status':self.status,'ended_reason':self.ended_reason,'returned':self.returned,
            'completed_ids':self.completed.copy(),'completed_count':len(self.completed),'task_count':len(self.scenario.tasks),
            'raw_value':value,'effective_value':value if self.returned and margin>=-1e-7 else 0,
            'initial_wh':self.initial_wh,'consumed_wh':self.consumed_wh,'remaining_wh':self.remaining_wh,
            'reserve_wh':self.reserve_wh,'reserve_margin_wh':margin,'consumed_ah':self.q-self.initial_q,
            't_s':self.t_s,'distance_m':self.distance_m,'source':'LOCAL_2D_SIM','real_flight':False}

    def state(self):
        return {'id':self.id,'status':self.status,'stage':self.stage,'t_s':self.t_s,'speedup':self.speedup,
            'position':self.position.copy(),'grid':copy.deepcopy(self.grid),'base':list(self.scenario.base),
            'tasks':[t.model_dump(mode='json') for t in self.scenario.tasks],'completed_ids':self.completed.copy(),
            'path':copy.deepcopy(self.path),'executed_path':copy.deepcopy(self.executed_path),
            'current_decision':copy.deepcopy(self.decisions[-1]) if self.decisions else None,
            'decisions':copy.deepcopy(self.decisions),'events':copy.deepcopy(self.events),
            'response_metrics':copy.deepcopy(self.response_metrics),'pending_replan':bool(self._pending),
            'summary':self.summary(),'source':'LOCAL_2D_SIM','runtime_version':RUNTIME_VERSION,
            'scenario_label':self.scenario.label,'temperature_c':self.config.temperature_c,
            'initial_soc':self.config.initial_soc,'error_profile':self.config.error_profile,
            'selector_id':self.config.selector_id,'budget_mode':self.config.budget_mode,
            'queued_manual_events':sum(source=='manual' for _,source,_ in self._queue)}

    def export(self):
        config=self.config.model_dump(mode='json')
        config['manual_events']=[e.model_dump(mode='json') for e in self._manual]
        config['cancel_after_s']=self._cancel_after
        deterministic={'summary':self.summary(),'telemetry':self.telemetry,'events':self.events,'intervals':self.intervals,
            'decisions':[{**d,'record':{k:v for k,v in d['record'].items() if k!='computation_ms'}} for d in self.decisions]}
        return {'metadata':{'runtime_version':RUNTIME_VERSION,'selector_version':SELECTOR_VERSION,'source':'LOCAL_2D_SIM',
                           'curve_sha256':self.library.sha256,'curve_source':self.library.source,
                           'source_sha256':self._source_hashes,
                           'reference_conditions':{'current_a':4.2,'series_cells':4,'fixed_step_s':STEP_S,
                               'model':'ideal_constant_current_reference_not_real_aircraft'},
                           'seed_usage':'recorded_no_random_draws_in_this_version'},
            'configuration':config,'configuration_sha256':fingerprint(config),'state':self.state(),
            'summary':self.summary(),'telemetry':copy.deepcopy(self.telemetry),'events':copy.deepcopy(self.events),
            'decisions':copy.deepcopy(self.decisions),'intervals':copy.deepcopy(self.intervals),
            'response_metrics':copy.deepcopy(self.response_metrics),'result_sha256':fingerprint(deterministic)}
