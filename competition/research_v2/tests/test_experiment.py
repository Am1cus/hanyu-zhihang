"""Analysis gates keep failures, refusals and losing comparisons visible."""
import unittest
from competition.research_v2.experiment import aggregate


class ExperimentAnalysisTests(unittest.TestCase):
    def test_refusal_and_worker_errors_stay_in_denominator(self):
        success={'process_status':'ok','summary':{'returned':True,'reserve_margin_wh':1.,'status':'PARTIAL_RETURNED',
            'distance_m':100.,'effective_value':5,'completed_count':1,'consumed_wh':3.},
            'task_total_value':10,'decision_ms':[1.]}
        refusal={**success,'summary':{**success['summary'],'returned':False,'status':'REFUSED',
            'distance_m':0.,'effective_value':0,'completed_count':0,'consumed_wh':0.}}
        failure={'process_status':'timeout','summary':None,'decision_ms':[]}
        report=aggregate([success,refusal,failure])
        self.assertEqual(report['n'],3)
        self.assertEqual(report['not_returned'],2)
        self.assertEqual(report['refused'],1)
        self.assertEqual(report['worker_errors'],1)
        self.assertAlmostEqual(report['mean_effective_score'],50/3)


if __name__=='__main__':unittest.main()
