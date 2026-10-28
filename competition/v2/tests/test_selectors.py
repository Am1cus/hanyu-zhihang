"""Independent small-case checks of task selection, without flight execution."""
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from competition.v2.contracts import DecisionRequest, LegEstimate, fingerprint, validate_decision_for_request
from competition.v2.planning_inputs import assess_order, build_leg_table
from competition.v2.reference import brute_force_reference
from competition.v2.scenarios import development_scenarios, initial_request
from competition.v2.selectors import decide, select_order

SELECTORS = ('fixed_order', 'nearest_feasible', 'value_per_cost', 'subset_dp')


class SelectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maps = development_scenarios()

    def request(self, **changes):
        return initial_request(self.maps[0], **changes)

    def revised(self, request, section, **changes):
        data = request.model_dump(mode='json')
        data[section].update(changes)
        return DecisionRequest.model_validate(data)

    def test_both_maps_and_budget_modes_match_independent_enumeration(self):
        for scene in self.maps:
            for mode in ('nominal', 'bounded'):
                with self.subTest(scene=scene.id, mode=mode):
                    request = initial_request(scene, temperature_c=-20., budget_mode=mode)
                    record = decide(request)
                    reference = brute_force_reference(request)
                    values = {t.id:t.value for t in request.task_catalog}
                    self.assertEqual(sum(values[t] for t in record.ordered_task_ids), reference['best_value'])
                    self.assertAlmostEqual(sum((record.budget.transit_wh, record.budget.service_wh,
                                               record.budget.return_wh)), reference['route_wh'], places=7)
                    self.assertEqual(reference['enumerated_orders'], 326 if len(scene.tasks)==5 else 109601)

    def test_all_policies_are_feasible_and_account_for_all_tasks(self):
        for selector in SELECTORS:
            request = self.request(selector=selector, temperature_c=-20.)
            record = decide(request)
            self.assertIs(validate_decision_for_request(request, record), record)
            self.assertEqual(record.budget.status, 'SUFFICIENT')
            self.assertEqual(set(record.ordered_task_ids) | {t.id for t in record.deferred_tasks},
                             {t.id for t in request.task_catalog})
            self.assertEqual(assess_order(request, build_leg_table(request), record.ordered_task_ids), record.budget)

    def test_repeatability_excludes_only_wall_clock_time_and_does_not_mutate_input(self):
        for selector in SELECTORS:
            request = self.request(selector=selector)
            before = fingerprint(request)
            first, second = decide(request), decide(request)
            self.assertEqual(first.model_dump(exclude={'computation_ms'}), second.model_dump(exclude={'computation_ms'}))
            self.assertEqual(before, fingerprint(request))

    def test_completed_tasks_are_not_selected_or_deferred(self):
        for selector in SELECTORS:
            request = self.revised(self.request(selector=selector), 'observation', completed_task_ids=['A','C'])
            record = decide(request)
            self.assertFalse({'A','C'} & (set(record.ordered_task_ids) | {t.id for t in record.deferred_tasks}))
            validate_decision_for_request(request, record)

    def test_complete_catalog_has_return_plan_without_claiming_arrival(self):
        request = self.revised(self.request(), 'observation', completed_task_ids=['A','B','C','D','E'])
        record = decide(request)
        self.assertEqual((record.action, record.reason_code), ('RETURN','ALL_TASKS_VISITED'))
        self.assertFalse(record.budget.execution_verified)
        self.assertEqual(record.deferred_tasks, ())

    def test_low_energy_at_base_refuses_and_away_stops(self):
        for selector in SELECTORS:
            request = self.request(selector=selector, initial_soc=.1)
            self.assertEqual(decide(request).action, 'REFUSED')
            away = self.revised(request, 'observation', position=[10,3])
            record = decide(away)
            self.assertEqual((record.action, record.reason_code), ('STOP','RETURN_BUDGET_INSUFFICIENT'))

    def test_out_of_range_temperature_is_data_unavailable(self):
        for selector in SELECTORS:
            record = decide(self.request(selector=selector, temperature_c=-30.))
            self.assertEqual((record.action,record.reason_code), ('STOP','DATA_UNAVAILABLE'))
            self.assertIsNone(record.budget.margin_wh)
            self.assertTrue(all(t.reason=='DATA_UNAVAILABLE' for t in record.deferred_tasks))

    def test_disconnected_return_stops_instead_of_teleporting(self):
        request = self.request()
        value = request.model_dump(mode='json')
        grid = value['observation']['known_map']
        grid['blocked'] = [[6,y] for y in range(grid['height'])]
        value['observation'].update(position=[10,3], known_map_sha256=fingerprint(grid))
        record = decide(DecisionRequest.model_validate(value))
        self.assertEqual((record.action,record.reason_code), ('STOP','RETURN_UNREACHABLE'))
        self.assertIsNone(record.budget.return_wh)

    def teaching(self, mode):
        fixture = json.loads((Path(__file__).resolve().parents[1]/'fixtures/day1_example.json').read_text())
        data = self.request(budget_mode=mode).model_dump(mode='json')
        data['observation']['available_wh_estimate'] = 11.
        data['budget']['reserve_wh'] = 2.
        data['model']['estimated_power_w'] = 180.
        request = DecisionRequest.model_validate(data)  # 10 s service = 0.5 Wh.
        nodes = ('CURRENT','BASE','A','B','C','D','E')
        positions = fixture['positions']
        legs = {}
        for a in nodes:
            for b in nodes:
                x,y=positions['S' if a in ('CURRENT','BASE') else a]
                xx,yy=positions['S' if b in ('CURRENT','BASE') else b]
                energy = abs(xx-x)*(1. if xx>=x else 1.2)+abs(yy-y)
                legs[a,b]=LegEstimate(from_id=a,to_id=b,status='PLANNED',path=((x,y),(xx,yy)),
                    distance_m=float(abs(xx-x)+abs(yy-y)),duration_s=energy*20.,energy_wh=float(energy),reason=None)
        return request,legs,fixture

    def test_handcheck_nominal_and_bounded_and_directional_return(self):
        for mode in ('nominal','bounded'):
            request,legs,fixture = self.teaching(mode)
            order = select_order(request,legs)
            reference = brute_force_reference(request,legs)
            self.assertEqual(list(order),fixture['expected'][mode]['route'])
            self.assertEqual(reference['best_order'],list(order))
            self.assertAlmostEqual(reference['route_wh'],float(fixture['expected'][mode]['route_wh']))
            self.assertAlmostEqual(legs['A','BASE'].energy_wh,1.2)

    def test_strong_greedy_can_equal_dp_and_fixed_stops_at_next_unaffordable(self):
        request,legs,_=self.teaching('nominal')
        greedy=request.model_copy(update={'selector_id':'value_per_cost'})
        self.assertEqual(select_order(greedy,legs),select_order(request,legs))
        data=request.model_dump(mode='json')
        data['selector_id']='fixed_order'
        data['task_catalog']=[data['task_catalog'][3],*data['task_catalog'][:3],data['task_catalog'][4]]
        data['observation']['available_wh_estimate']=5.
        fixed=DecisionRequest.model_validate(data)
        self.assertEqual(select_order(fixed,legs),())
        self.assertEqual(assess_order(fixed,legs,['A']).status,'SUFFICIENT')

    def test_exact_ties_choose_stable_ids(self):
        request,legs,_=self.teaching('nominal')
        data=request.model_dump(mode='json')
        data['budget']['reserve_wh']=0.
        data['observation']['available_wh_estimate']=3.
        for task in data['task_catalog']: task.update(value=1,dwell_s=0.)
        request=DecisionRequest.model_validate(data)
        for key,leg in list(legs.items()):
            legs[key]=leg.model_copy(update={'energy_wh':0. if key[0]==key[1] else 1.})
        self.assertEqual(select_order(request,legs),('A','B'))
        self.assertEqual(brute_force_reference(request,legs)['best_order'],['A','B'])

    def test_reference_rejects_missing_edge_instead_of_zero_cost(self):
        request,legs,_=self.teaching('nominal')
        del legs['C','BASE']
        self.assertEqual(brute_force_reference(request,legs)['status'],'DATA_UNAVAILABLE')


if __name__=='__main__':
    unittest.main()
