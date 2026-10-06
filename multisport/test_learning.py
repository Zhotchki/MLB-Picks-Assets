import unittest
from datetime import date
from update import learn,group
from test_validation import row

class LearningTests(unittest.TestCase):
    def test_improvement_in_one_sport_cannot_hide_harm_in_another(self):
        rows=[]
        for day in range(50):
            for player in range(10):
                rows.append(dict(row(day,player,sport='MLB',probability=.05),baselineVersion=None,prop='Hits'))
                y=1 if day<40 else 0
                rows.append(row(day,player,sport='NHL',probability=.05,outcome=y))
        nhl=group(rows[1]);mlb=group(rows[0]);incumbent={'version':'baseline','offsets':{nhl:.03}}
        updated=learn(rows,incumbent,date(2026,12,7))
        self.assertEqual(updated['review']['status'],'PROMOTED')
        self.assertEqual(updated['offsets'][nhl],.03)
        self.assertGreater(updated['offsets'][mlb],0)
        self.assertEqual(updated['review']['groupReviews'][nhl]['status'],'KEPT_CURRENT_GROUP')
        self.assertEqual(updated['review']['acceptedGroups'],[mlb])
        self.assertEqual(incumbent['offsets'],{nhl:.03})

    def test_threshold_rows_cannot_replace_player_game_support(self):
        rows=[row(d,p,t) for d in range(50) for p in range(4) for t in (1,2,3,4,5)]
        updated=learn(rows,{'version':'baseline','offsets':{}},date(2026,12,7))
        self.assertEqual(updated['review']['status'],'COLLECTING_RESULTS')
        self.assertEqual(updated['review']['trainingPlayerGames'],160)
        self.assertEqual(updated['review']['trainingRows'],800)

    def test_changed_source_version_uses_different_calibration_group(self):
        a=row();b=dict(a,baselineVersion='shots-2')
        self.assertNotEqual(group(a),group(b))

    def test_already_used_holdout_cannot_promote(self):
        rows=[row(d,p,probability=.05) for d in range(50) for p in range(10)]
        updated=learn(rows,{'version':'baseline','offsets':{},'trainedThrough':rows[-1]['startTime']},date(2026,12,7))
        self.assertEqual(updated['version'],'baseline');self.assertFalse(updated['review']['freshHoldout'])
        self.assertEqual(updated['review']['acceptedGroups'],[])

if __name__=='__main__':unittest.main()
