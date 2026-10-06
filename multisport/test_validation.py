import unittest
from datetime import datetime,timedelta,timezone
from validation import report,score,chronological,graded,holdout,support

def row(day=0,player=1,target=3,sport='NHL',outcome=1,probability=.8):
    start=datetime(2026,10,1,23,tzinfo=timezone.utc)+timedelta(days=day)
    return {'id':f'{sport}:{day}:{player}:{target}','sport':sport,'gameId':day,'playerId':player,
            'prop':'Shots on Goal','direction':'MORE','baselineVersion':'shots-1','modelVersion':'baseline',
            'target':target,'probability':probability,'sourceProbability':probability,'projection':3.5,
            'capturedAt':(start-timedelta(hours=1)).isoformat(),'startTime':start.isoformat(),
            'gradedAt':(start+timedelta(hours=3)).isoformat(),'resultStatus':'GRADED','outcome':outcome,'actual':5 if outcome else 0}

class ValidationTests(unittest.TestCase):
    def group(self,r):return next(g for g in report(r)['groups'] if g['sport']=='NHL' and g['recorded']['forecasts'])
    def test_multiple_thresholds_are_one_player_game_and_one_projection_error(self):
        r=[row(target=t) for t in (1,2,3,4,5)]
        g=self.group(r);self.assertEqual(g['recorded']['forecasts'],5)
        self.assertEqual(g['graded']['playerGames'],1);self.assertEqual(g['graded']['games'],1)
        self.assertEqual(g['projectionErrors']['playerGames'],1);self.assertEqual(g['projectionErrors']['mae'],1.5)

    def test_scores_balance_games_instead_of_counting_targets_as_independent(self):
        rows=[row(day=0,target=t,outcome=0,probability=.1) for t in range(1,101)]
        rows += [row(day=1,player=p,outcome=0,probability=.9) for p in range(10)]
        self.assertAlmostEqual(score(rows)['brier'],.41)

    def test_duplicate_capture_keeps_first_frozen_probability(self):
        first=row();later=dict(first,probability=.2,capturedAt=first['startTime'])
        result=report([later,first,first]);self.assertEqual(result['duplicateForecasts'],1)
        self.assertEqual(result['invalidForecasts'],1);self.assertEqual(self.group([later,first])['scores']['meanProbability'],.8)

    def test_source_and_calibrator_versions_do_not_mix(self):
        a=row();b=dict(row(day=1),baselineVersion='shots-2');c=dict(row(day=2),modelVersion='weekly-2')
        groups=[g for g in report([a,b,c])['groups'] if g['sport']=='NHL']
        self.assertEqual(len(groups),3);self.assertTrue(all(g['graded']['playerGames']==1 for g in groups))

    def test_holdout_keeps_all_players_and_targets_of_game_together(self):
        rows=[row(day=d,player=p,target=t) for d in range(10) for p in range(3) for t in (1,2,3)]
        a,b=chronological(rows);self.assertFalse({r['gameId'] for r in a}&{r['gameId'] for r in b})
        self.assertEqual({r['gameId'] for r in b},{8,9})

    def test_grade_must_be_final_consistent_and_pregame(self):
        a=row();b=dict(a,actual=0);c=dict(a,gradedAt=a['capturedAt'])
        self.assertTrue(graded(a));self.assertFalse(graded(b));self.assertFalse(graded(c))
        g=self.group([b]);self.assertEqual(g['graded']['forecasts'],0);self.assertEqual(g['invalidResults'],1)

    def test_fractional_nfl_line_is_strictly_greater_than_real_line(self):
        a=dict(row(sport='NFL'),actual=14.7,modelLine=14.5,target=15)
        self.assertTrue(graded(a));self.assertFalse(graded(dict(a,actual=14.5)))

    def test_many_thresholds_cannot_satisfy_player_game_or_event_support(self):
        rows=[row(target=t,outcome=0) for t in range(1,1001)]
        r=holdout(rows);self.assertEqual(r['status'],'COLLECTING_SEPARATE_GAMES')
        self.assertEqual(r['holdout']['playerGames'],1)

    def test_reference_fitted_only_on_training_outcomes_and_no_auto_eligibility(self):
        rows=[]
        for day in range(50):
            for player in range(10):
                y=player%2 if day<40 else 0
                rows.extend(row(day,player,t,outcome=y,probability=.9 if y else .1) for t in (3,4))
        g=self.group(rows);review=g['review']
        self.assertEqual(review['status'],'REVIEWABLE_HOLDOUT');self.assertEqual(review['holdout']['playerGames'],100)
        self.assertAlmostEqual(review['referenceScores']['meanProbability'],.5)
        self.assertTrue(review['beatsReference']);self.assertFalse(g['enablesPlayableOffers'])

    def test_pending_void_and_empty_sports_are_reported_without_fake_accuracy(self):
        rows=[dict(row(),resultStatus='PENDING'),dict(row(day=1),resultStatus='VOID')]
        g=self.group(rows);self.assertEqual(g['pending'],1);self.assertEqual(g['void'],1)
        self.assertIsNone(g['scores']['brier']);self.assertEqual(g['status'],'COLLECTING_RESULTS')
        result=report(rows);self.assertEqual(result['sports']['NBA']['recorded']['forecasts'],0)
        self.assertEqual(len([g for g in result['groups'] if g['sport']=='NBA']),4)

    def test_game_dates_use_user_timezone_not_utc_midnight(self):
        a=row();start=datetime(2026,10,2,2,tzinfo=timezone.utc)
        b=dict(row(day=1),startTime=start.isoformat(),capturedAt=(start-timedelta(hours=1)).isoformat(),gradedAt=(start+timedelta(hours=3)).isoformat())
        self.assertEqual(support([a,b])['games'],2);self.assertEqual(support([a,b])['days'],1)

    def test_unknown_timezone_and_missing_grade_time_are_not_evidence(self):
        a=row();a['capturedAt']='2026-10-01T20:00:00';a['startTime']='2026-10-01T23:00:00'
        self.assertEqual(report([a])['invalidForecasts'],1)
        self.assertFalse(graded(dict(row(),gradedAt=None)))

if __name__=='__main__':unittest.main()
