import json
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from pydantic import ValidationError

from competition.v2.api import create_app
from competition.v2.contracts import fingerprint
from competition.v2.runtime import RuntimeConfig,RuntimeRun,preset_config
from competition.research_v2.adaptive import CandidateConfig,CandidateRun,past_power
from competition.research_v2.scenarios import generate,with_events
from competition.research_v2.path_reference import dijkstra_energy
from competition.v2.planning_inputs import build_leg_table
from competition.v2.scenarios import initial_request


class CandidateTests(unittest.TestCase):
    def test_only_completed_past_intervals_contribute(self):
        row={'start_s':0.,'end_s':10.,'integrated_wh':.2,'partial':False}
        self.assertEqual(past_power(50.,[],10.),50.)
        self.assertEqual(past_power(80.,[row],10.),80.)
        self.assertEqual(past_power(50.,[row],10.),72.)
        self.assertEqual(past_power(50.,[row],9.),50.)
        self.assertEqual(past_power(50.,[{**row,'partial':True}],10.),50.)

    def test_first_decision_and_initial_physics_match(self):
        config=preset_config('normal',initial_soc=.35,error_profile='joint_outside_declared')
        baseline=RuntimeRun(config);candidate=CandidateRun(CandidateConfig(base_configuration=config))
        self.assertEqual(candidate.decisions[0]['request'],baseline.decisions[0]['request'])
        self.assertEqual((candidate.initial_wh,candidate.reserve_wh,candidate.q),
                         (baseline.initial_wh,baseline.reserve_wh,baseline.q))
        baseline.advance(1.);candidate.advance(1.)
        self.assertEqual(candidate.telemetry,baseline.telemetry)
        self.assertEqual(candidate.config,baseline.config)

    def test_powers_follow_past_rule_and_replay_is_exact(self):
        config=preset_config('obstacle',initial_soc=.55,error_profile='joint_outside_declared')
        run=CandidateRun(CandidateConfig(base_configuration=config)).run_all()
        self.assertGreater(len(run.decisions),1)
        for decision in run.decisions:
            expected=past_power(run.initial_planning_power,run.intervals,decision['t_s'])
            # The archive also contains intervals ending at this timestamp;
            # _choose is called after those intervals are completed.
            self.assertAlmostEqual(decision['request']['model']['estimated_power_w'],expected)
            self.assertEqual(decision['request']['budget'],run.template.budget.model_dump(mode='json'))
        archive=run.export()
        repeated=CandidateRun(CandidateConfig.model_validate(archive['configuration'])).run_all()
        self.assertEqual(repeated.export()['result_sha256'],archive['result_sha256'])
        self.assertEqual(fingerprint(archive['configuration']),archive['configuration_sha256'])
        with self.assertRaises(ValidationError):RuntimeConfig.model_validate(archive['configuration'])

    def test_default_http_replay_rejects_candidate(self):
        with tempfile.TemporaryDirectory() as directory:
            app=create_app(Path(directory)/'test.sqlite3',tick_enabled=False)
            with TestClient(app) as client:
                candidate=CandidateRun(CandidateConfig(base_configuration=preset_config('low_budget')))
                app.state.store.save(candidate)
                self.assertEqual(client.post('/api/v2/runs/'+candidate.id+'/replay').status_code,409)

    def test_generator_is_reproducible_and_future_events_hidden(self):
        entry=generate(2026111300,0)
        self.assertEqual(entry,generate(2026111300,0))
        self.assertEqual(len(entry['scenario']['tasks']),5)
        self.assertEqual(len(generate(2026111301,1)['scenario']['tasks']),8)
        normal=RuntimeConfig(scenario=with_events(entry,'normal'))
        event=normal.model_copy(update={'scenario':with_events(entry,'wind_then_obstacle')})
        a=CandidateRun(CandidateConfig(base_configuration=normal))
        b=CandidateRun(CandidateConfig(base_configuration=event))
        self.assertEqual(a.decisions[0]['request'],b.decisions[0]['request'])

    def test_independent_path_reference_handles_direction_and_disconnection(self):
        scene=with_events(generate(2026111300,0),'normal')
        request=initial_request(scene);legs=build_leg_table(request)
        for target in scene.tasks:
            expected=dijkstra_energy(scene.grid,scene.base,target.position,5.,request.model.estimated_power_w)
            self.assertAlmostEqual(legs['BASE',target.id].energy_wh,expected)
        blocked=scene.grid.model_copy(update={'blocked':tuple((2,y) for y in range(16))})
        self.assertIsNone(dijkstra_energy(blocked,(1,8),(3,8),5.,70.56))


if __name__=='__main__':unittest.main()
