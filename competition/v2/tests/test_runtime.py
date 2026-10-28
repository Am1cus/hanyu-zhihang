"""Execution, provenance, event effects, failure and replay checks."""
import copy
import tempfile
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from competition.v2.api import create_app
from competition.v2.contracts import fingerprint
from competition.v2.runtime import RuntimeConfig, RuntimeRun, TERMINAL, preset_config


class RuntimeTests(unittest.TestCase):
    def run_case(self,preset='normal',**options):
        return RuntimeRun(preset_config(preset,**options))

    def assert_energy(self,run):
        integrated=sum(t['average_voltage_v']*t['current_a']*t['dt_s']/3600 for t in run.telemetry)
        ah=sum(t['current_a']*t['dt_s']/3600 for t in run.telemetry)
        self.assertAlmostEqual(integrated,run.consumed_wh,places=7)
        self.assertAlmostEqual(ah,run.q-run.initial_q,places=7)
        self.assertAlmostEqual(run.initial_wh-run.consumed_wh,run.remaining_wh,places=7)
        self.assertAlmostEqual(run.curve.energy_between(run.q,run.curve.capacity_ah),run.remaining_wh,places=7)

    def test_all_selectors_return_after_actual_movement(self):
        for method in ('fixed_order','nearest_feasible','value_per_cost','subset_dp'):
            with self.subTest(method=method):
                run=self.run_case(selector_id=method).run_all()
                self.assertIn(run.status,{'COMPLETED_RETURNED','PARTIAL_RETURNED'})
                self.assertTrue(run.returned)
                self.assertEqual(run.position,list(run.scenario.base))
                self.assertGreater(run.distance_m,0)
                self.assertEqual(len(run.completed),len(set(run.completed)))
                self.assertGreaterEqual(run.summary()['reserve_margin_wh'],-1e-7)
                self.assert_energy(run)

    def test_visit_requires_completed_dwell_not_arrival(self):
        run=self.run_case(selector_id='value_per_cost')
        arrival=run.decisions[0]['planned_legs'][0]['duration_s']
        run.advance(arrival)
        self.assertEqual(run.stage,'DWELL');self.assertEqual(run.completed,[])
        run.advance(9.5);self.assertEqual(run.completed,[])
        run.advance(.5);self.assertEqual(len(run.completed),1)

    def test_chunking_and_speed_do_not_change_deterministic_result(self):
        full=self.run_case('obstacle',selector_id='value_per_cost').run_all()
        chunked=self.run_case('obstacle',selector_id='value_per_cost',speedup=50.)
        while chunked.status=='RUNNING': chunked.advance(3.7)
        self.assertEqual(full.export()['result_sha256'],chunked.export()['result_sha256'])

    def test_obstacle_changes_plan_and_actual_trajectory(self):
        normal=self.run_case(selector_id='value_per_cost').run_all()
        blocked=self.run_case('obstacle',selector_id='value_per_cost').run_all()
        self.assertTrue(blocked.response_metrics[0]['plan_changed'])
        self.assertTrue(blocked.events[0]['applied'])
        self.assertNotEqual(normal.executed_path,blocked.executed_path)
        self.assertNotEqual(normal.distance_m,blocked.distance_m)
        for sample in blocked.telemetry:
            if sample['t_s']>=32:
                self.assertNotEqual(sample['position'],[8,3])
        self.assert_energy(blocked)

    def test_gust_changes_execution_time_and_energy(self):
        normal=self.run_case(selector_id='value_per_cost').run_all()
        gust=self.run_case('gust',selector_id='value_per_cost').run_all()
        self.assertTrue(gust.response_metrics[0]['plan_changed'])
        self.assertGreater(gust.t_s,normal.t_s)
        self.assertGreater(gust.consumed_wh,normal.consumed_wh)
        self.assert_energy(gust)

    def test_future_event_cannot_change_initial_decision_request(self):
        normal=self.run_case(selector_id='value_per_cost')
        blocked=self.run_case('obstacle',selector_id='value_per_cost')
        self.assertEqual(normal.decisions[0]['request'],blocked.decisions[0]['request'])
        self.assertNotIn('scheduled_events',str(normal.decisions[0]['request']))

    def test_noop_event_is_not_a_behavior_change_from_shorter_remaining_path(self):
        config=preset_config('normal',selector_id='value_per_cost').model_dump(mode='json')
        config['scenario']['scheduled_events']=[{'id':'same-wind','at_s':3.,'type':'wind','region_id':'east','vector':[-1.5,0.]}]
        run=RuntimeRun(RuntimeConfig.model_validate(config))
        run.advance(16.)
        response=run.response_metrics[0]
        self.assertFalse(response['plan_changed'])
        self.assertFalse(response['budget_changed'])
        self.assertEqual(response['same_state_counterfactual']['scope'],'same_current_state_with_map_before_joint_pending_events')

    def test_mid_edge_event_waits_for_actual_node(self):
        config=preset_config('normal',selector_id='value_per_cost').model_dump(mode='json')
        config['scenario']['scheduled_events']=[{'id':'mid-edge','at_s':3.,'type':'wind','region_id':'east','vector':[-4.,0.]}]
        run=RuntimeRun(RuntimeConfig.model_validate(config))
        run.advance(3.)
        self.assertTrue(run._pending)
        with self.assertRaisesRegex(ValueError,'actual_grid_node'):run.current_request()
        run.advance(13.)
        self.assertAlmostEqual(run.response_metrics[0]['simulated_delay_s'],13.)
        self.assertEqual(run.decisions[-1]['request']['observation']['position'],[2,5])

    def test_new_exclusion_on_executing_edge_fails_without_teleport(self):
        config=preset_config('normal',selector_id='value_per_cost').model_dump(mode='json')
        config['scenario']['scheduled_events']=[{'id':'occupied','at_s':4.,'type':'obstacle','cells':[[2,5]]}]
        run=RuntimeRun(RuntimeConfig.model_validate(config)).run_all()
        self.assertEqual(run.ended_reason,'occupied_edge_became_excluded')
        self.assertFalse(run.returned);self.assertEqual(run.completed,[])
        self.assertEqual(run.position,[2.,5.75])
        self.assertEqual(run.summary()['effective_value'],0)

    def test_refused_unavailable_and_extreme_failure_are_not_returned(self):
        for preset,status in (('low_budget','REFUSED'),('unavailable','UNAVAILABLE'),('blocked_return','FAILED')):
            run=self.run_case(preset,selector_id='value_per_cost').run_all()
            self.assertEqual(run.status,status)
            self.assertFalse(run.returned)
            self.assertEqual(run.summary()['effective_value'],0)

    def test_pause_cancel_and_cancel_replay(self):
        run=self.run_case(selector_id='value_per_cost')
        run.advance(3.7);before=run.t_s
        run.control('pause');run.advance(100.)
        self.assertEqual(run.t_s,before)
        run.control('resume');run.advance(2.3)
        run.control('cancel');archive=run.export()
        replay=RuntimeRun(RuntimeConfig.model_validate(archive['configuration'])).run_all()
        self.assertEqual(run.status,'CANCELLED');self.assertFalse(run.returned)
        self.assertEqual(archive['result_sha256'],replay.export()['result_sha256'])

    def test_manual_queued_event_replays_at_same_step(self):
        run=self.run_case(selector_id='value_per_cost')
        run.advance(3.7)
        queued=run.inject({'type':'obstacle','cells':[[8,3]]})
        self.assertEqual(queued['scheduled_at_s'],4.)
        run.run_all();archive=run.export()
        replay=RuntimeRun(RuntimeConfig.model_validate(archive['configuration'])).run_all()
        self.assertEqual(archive['result_sha256'],replay.export()['result_sha256'])
        self.assertEqual(run.events[0]['source'],'manual')

    def test_profiles_are_observation_errors_not_modified_physical_discharge(self):
        for profile in ('joint_within_declared','joint_outside_declared'):
            for mode in ('nominal','bounded'):
                run=self.run_case(error_profile=profile,budget_mode=mode,initial_soc=.55).run_all()
                self.assertTrue(all(t['current_a']==4.2 for t in run.telemetry))
                self.assert_energy(run)
                self.assertEqual(run.export()['metadata']['source'],'LOCAL_2D_SIM')

    def test_intervals_cover_all_integrated_energy_and_record_out_of_range(self):
        run=self.run_case('gust',selector_id='value_per_cost').run_all()
        self.assertAlmostEqual(sum(x['integrated_wh'] for x in run.intervals),run.consumed_wh,places=7)
        self.assertTrue(all(x['end_s']>=x['start_s'] for x in run.intervals))
        self.assertTrue(all(isinstance(x['covered'],bool) for x in run.intervals if not x['partial']))


class RuntimeApiTests(unittest.TestCase):
    def test_preview_has_no_persisted_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            with TestClient(create_app(Path(tmp)/'test.db',tick_enabled=False)) as client:
                preview=client.post('/api/v2/preview',json={}).json()
                self.assertTrue(preview['is_preview'])
                self.assertEqual(client.get('/api/v2/runs').json(),[])

    def test_export_restart_and_replay_keep_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.db'
            app=create_app(path,tick_enabled=False)
            with TestClient(app) as client:
                state=client.post('/api/v2/runs',json={'preset':'obstacle'}).json();run=app.state.runs[state['id']]
                run.run_all();app.state.store.save(run)
                exported=client.get('/api/v2/runs/'+run.id+'/export').json()
                self.assertEqual(exported['configuration_sha256'],fingerprint(exported['configuration']))
            reopened=create_app(path,tick_enabled=False)
            with TestClient(reopened) as client:
                saved=client.get('/api/v2/runs/'+run.id).json()
                self.assertFalse(saved['runtime_available'])
                self.assertEqual(client.post('/api/v2/runs/'+run.id+'/control',json={'action':'resume'}).status_code,409)
                new=client.post('/api/v2/runs/'+run.id+'/replay',json={}).json()
                replay=reopened.state.runs[new['id']];replay.run_all();reopened.state.store.save(replay)
                result=client.get('/api/v2/runs/'+new['id']+'/export').json()
                self.assertEqual(result['result_sha256'],exported['result_sha256'])
                self.assertEqual(result['execution_audit']['origin']['source_run_id'],run.id)

    def test_controls_event_queue_and_invalid_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            app=create_app(Path(tmp)/'test.db',tick_enabled=False)
            with TestClient(app) as client:
                state=client.post('/api/v2/runs',json={'preset':'normal'}).json();run_id=state['id']
                queued=client.post('/api/v2/runs/'+run_id+'/events',json={'kind':'obstacle_ahead'})
                self.assertEqual(queued.status_code,200)
                self.assertEqual(queued.json()['status'],'QUEUED')
                paused=client.post('/api/v2/runs/'+run_id+'/control',json={'action':'pause'})
                self.assertEqual(paused.json()['status'],'PAUSED')
                self.assertEqual(client.post('/api/v2/runs',json={'invented':'field'}).status_code,422)
                self.assertEqual(client.post('/api/v2/runs/'+run_id+'/events',json={'kind':'delete_all'}).status_code,422)
                client.post('/api/v2/runs/'+run_id+'/control',json={'action':'cancel'})
                self.assertEqual(client.post('/api/v2/runs/'+run_id+'/events',json={'kind':'gust'}).status_code,409)


if __name__=='__main__':unittest.main()
