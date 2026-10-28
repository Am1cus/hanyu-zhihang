"""The policy must act before the first decision and remain replayable."""
import unittest
from types import SimpleNamespace
from pydantic import ValidationError
from competition.core.curves import CurveLibrary
from competition.v2.runtime import RuntimeConfig, RuntimeRun, preset_config
from competition.v2.reserve_sensitivity import ReserveRun, SensitivityConfig


class ReserveSensitivityTests(unittest.TestCase):
    def run_case(self, fraction, preset='normal'):
        return ReserveRun(SensitivityConfig(base_configuration=preset_config(preset), reserve_fraction=fraction))

    def test_twenty_percent_preserves_all_development_outcomes_exactly(self):
        for preset in ('normal','obstacle','gust','low_budget','unavailable','blocked_return'):
            with self.subTest(preset=preset):
                original=RuntimeRun(preset_config(preset)).run_all().export()
                adapted=self.run_case(.2,preset).run_all().export()
                self.assertEqual(original['result_sha256'],adapted['result_sha256'])

    def test_reserve_applies_before_first_and_subsequent_decisions(self):
        for fraction in (.1,.3):
            run=self.run_case(fraction,'obstacle').run_all()
            expected=CurveLibrary().reference_wh*fraction
            self.assertEqual(run.reserve_wh,expected)
            self.assertGreater(len(run.decisions),1)
            for row in run.decisions:
                self.assertEqual(row['request']['budget']['reserve_wh'],expected)
                self.assertEqual(row['record']['budget']['reserve_wh'],expected)

    def test_reserve_does_not_change_physical_initial_energy_or_current(self):
        runs=[self.run_case(f).run_all() for f in (.1,.2,.3)]
        self.assertEqual(len({r.initial_wh for r in runs}),1)
        self.assertTrue(all(t['current_a']==4.2 for r in runs for t in r.telemetry))

    def test_stricter_initial_policy_cannot_increase_static_maximum_value(self):
        values=[]
        for fraction in (.1,.2,.3):
            base=preset_config('normal',initial_soc=.35,selector_id='subset_dp')
            run=ReserveRun(SensitivityConfig(base_configuration=base,reserve_fraction=fraction))
            order=run.decisions[0]['record']['ordered_task_ids']
            values.append(sum(t.value for t in run.scenario.tasks if t.id in order))
        self.assertEqual(values,sorted(values,reverse=True))

    def test_supplement_archive_requires_explicit_adapter_and_replays(self):
        run=self.run_case(.3,'obstacle').run_all();archive=run.export()
        with self.assertRaises(ValidationError):RuntimeConfig.model_validate(archive['configuration'])
        replay=ReserveRun(SensitivityConfig.model_validate(archive['configuration'])).run_all()
        self.assertEqual(archive['result_sha256'],replay.export()['result_sha256'])

    def test_manual_events_and_cancel_are_not_lost_in_export(self):
        run=self.run_case(.1);run.advance(3.7);run.inject({'type':'obstacle','cells':[[8,3]]})
        run.advance(20.);run.control('cancel');archive=run.export()
        replay=ReserveRun(SensitivityConfig.model_validate(archive['configuration'])).run_all()
        self.assertEqual(archive['result_sha256'],replay.export()['result_sha256'])

    def test_invalid_fraction_is_rejected(self):
        for value in (-.1,1.1,float('nan'),float('inf'),True,'0.2'):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                SensitivityConfig(base_configuration=preset_config(),reserve_fraction=value)

    def test_lowering_own_threshold_does_not_lower_common_comparison(self):
        from competition.v2.tools.evaluate_reserve import metrics
        fake=SimpleNamespace(library=SimpleNamespace(reference_wh=60.),
            scenario=SimpleNamespace(tasks=[SimpleNamespace(value=5)]),
            summary=lambda:{'raw_value':5,'effective_value':5,'returned':True,
                            'remaining_wh':9.,'reserve_margin_wh':3.})
        result=metrics(fake)
        self.assertEqual(result['own_threshold_value_fraction'],1.)
        self.assertEqual(result['fixed_20_value_fraction'],0.)
        self.assertFalse(result['fixed_20_pass'])

    def test_process_errors_remain_in_summary_denominator(self):
        from competition.v2.tools.evaluate_reserve import aggregate
        result=aggregate([{'execution':'ERROR'},{'execution':'TIMEOUT'}])
        self.assertEqual(result['n'],2)
        self.assertEqual(result['process_errors'],2)
        self.assertEqual(result['mean_fixed_20_value_fraction'],0.)
