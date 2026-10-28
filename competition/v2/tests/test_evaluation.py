"""Evaluation leakage, pairing, provenance and raw archive checks."""
import copy
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from pydantic import ValidationError
from competition.v2.contracts import fingerprint
from competition.v2.runtime import preset_config
from competition.v2.scenarios import Scenario, development_scenarios, initial_request
from competition.v2.tools.evaluate import maps, specifications, validate_matrix, worker, load_frozen, sha


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.maps=maps();cls.rows=specifications(cls.maps)

    def test_split_cannot_silently_relabel_a_development_map(self):
        scene=development_scenarios()[0].model_dump(mode='json');scene['split']='held_out'
        with self.assertRaisesRegex(ValidationError,'split_version_mismatch'):Scenario.model_validate(scene)

    def test_missing_or_duplicated_execution_is_rejected(self):
        with self.assertRaisesRegex(ValueError,'matrix_count'):validate_matrix(self.rows[:-1])
        rows=copy.deepcopy(self.rows);rows[-1]=rows[0]
        with self.assertRaisesRegex(ValueError,'duplicate_id'):validate_matrix(rows)

    def test_same_pair_cannot_receive_different_wind_or_battery(self):
        for field,value in [('initial_soc',.8),('seed',11)]:
            rows=copy.deepcopy(self.rows);rows[0]['configuration'][field]=value
            rows[0]['configuration_sha256']=fingerprint(rows[0]['configuration'])
            with self.assertRaisesRegex(ValueError,'unequal_information'):validate_matrix(rows)

    def test_result_labels_cannot_disagree_with_input(self):
        rows=copy.deepcopy(self.rows);rows[0]['temperature_c']=-20.
        with self.assertRaisesRegex(ValueError,'label_mismatch'):validate_matrix(rows)

    def test_future_variants_have_identical_initial_observation(self):
        for map_id in {r['map_id'] for r in self.rows}:
            rows=[r for r in self.rows if r['map_id']==map_id and r['temperature_c']==0. and
                  r['selector_id']=='subset_dp' and r['budget_mode']=='bounded' and
                  r['error_profile']=='no_added_bias' and r['kind']!='low_budget']
            requests=[initial_request(Scenario.model_validate(r['configuration']['scenario']),temperature_c=0.) for r in rows]
            self.assertEqual(len(requests),3)
            self.assertEqual(len({fingerprint(r) for r in requests}),1)

    def test_worker_retains_recomputable_telemetry_and_failure(self):
        # Only old development maps execute in this pre-freeze check.
        for preset in ('normal','low_budget'):
            with tempfile.TemporaryDirectory() as name:
                out=Path(name);config=preset_config(preset)
                row={'case_id':'DEV','configuration':config.model_dump(mode='json'),
                     'configuration_sha256':fingerprint(config)}
                (out/'configurations.jsonl').write_text(json.dumps(row)+'\n')
                worker(out,0)
                record=json.loads((out/'records/DEV.json').read_text())
                archive=json.loads(gzip.decompress((out/record['archive']).read_bytes()))
                self.assertTrue(record['checks']['passed'])
                self.assertEqual(record['archive_sha256'],sha(out/record['archive']))
                self.assertEqual(record['result_sha256'],archive['result_sha256'])
                self.assertAlmostEqual(sum(t['average_voltage_v']*t['current_a']*t['dt_s']/3600 for t in archive['telemetry']),archive['summary']['consumed_wh'],places=7)
                if preset=='low_budget':
                    self.assertEqual(record['summary']['status'],'REFUSED')
                    self.assertFalse(record['summary']['returned']);self.assertEqual(record['normalized_value'],0.)

    def test_tampering_with_frozen_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            out=Path(name);(out/'maps.json').write_text('original')
            body={'file_sha256':{'maps.json':sha(out/'maps.json')},'source_sha256':{}}
            body['freeze_sha256']=fingerprint(body);(out/'freeze.json').write_text(json.dumps(body))
            (out/'maps.json').write_text('changed')
            with self.assertRaisesRegex(ValueError,'frozen_input_changed'):load_frozen(out,False)


if __name__=='__main__':unittest.main()
