import unittest
from datetime import date
from update import number, prob, actual, learn, corrected
class AdapterTests(unittest.TestCase):
    def test_blank_and_nonfinite_are_not_zero(self):
        for v in ('',None,'nan','inf',True): self.assertIsNone(number(v))
        self.assertEqual(number(0),0)
    def test_zero_adjusted_probability_never_falls_back(self):
        self.assertIsNone(prob({'Adjusted Probability':0,'Probability':.8}))
        self.assertEqual(prob({'Adjusted Probability':'','Probability':.8}),.8)
    def test_missing_result_is_not_loss(self):
        self.assertIsNone(actual('Hits',{}))
        self.assertIsNone(actual('Hits + Runs + RBI',{'hits':1}))
        self.assertEqual(actual('Hits + Runs + RBI',{'hits':1,'runs':0,'rbi':2}),3)
    def test_learning_requires_support(self):
        m=learn([],{'version':'baseline','offsets':{}},date(2026,10,5))
        self.assertEqual(m['version'],'baseline')
        self.assertEqual(m['review']['status'],'COLLECTING_RESULTS')
    def test_week_review_idempotent(self):
        m={'version':'baseline','offsets':{},'lastReviewWeek':'2026-W41'}
        self.assertEqual(learn([],m,date(2026,10,5)),m)
    def test_clamp_probability(self):
        r={'sport':'MLB','prop':'Hits','direction':'MORE','sourceProbability':.9}
        self.assertEqual(corrected(r,{'offsets':{'MLB|Hits|MORE':1}}),.99)
if __name__=='__main__': unittest.main()
