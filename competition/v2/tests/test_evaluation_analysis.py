"""Missing pairs and negative results must not vanish in comparison summaries."""
import unittest
from competition.v2.tools.analyze_evaluation import paired


class AnalysisTests(unittest.TestCase):
    def test_missing_pair_is_error_not_an_exclusion(self):
        rows=[{'case_id':'a','condition_id':'one','budget_mode':'bounded',
               'selector_id':'subset_dp','normalized_value':1.}]
        with self.assertRaisesRegex(ValueError,'missing_pair'):paired(rows,'subset_dp','fixed_order')

    def test_ties_and_losses_retained_in_denominator(self):
        rows=[]
        for condition,(a,b) in enumerate(((.5,.3),(.6,.6),(0.,1.))):
            for method,value in [('subset_dp',a),('fixed_order',b)]:
                rows.append({'case_id':f'{condition}-{method}','condition_id':str(condition),
                    'budget_mode':'bounded','selector_id':method,'normalized_value':value})
        result=paired(rows,'subset_dp','fixed_order')
        self.assertEqual((result['n'],result['wins'],result['ties'],result['losses']),(3,1,1,1))
        self.assertAlmostEqual(result['mean_difference'],-.8/3)
        self.assertEqual(len(result['case_ids']['losses']),1)
