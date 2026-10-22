import unittest
from datetime import datetime,timedelta,timezone
from line_validation import report,apply
from line_pipeline import observed_valid

class ExactLineValidationTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2031,1,1,tzinfo=timezone.utc)
        self.rows=[]
        for game in range(50):
            start=datetime(2030,10,1,23,tzinfo=timezone.utc)+timedelta(days=game)
            for player in range(20):
                outcome=player%2;capture=start-timedelta(hours=1)
                self.rows.append(dict(id=f'line:{game}:{player}',forecastKind='SLEEPER_LINE',sport='NHL',gameId=game,playerId=player,prop='Shots on Goal',direction='MORE',modelLine=.5,target=1,probability=.9 if outcome else .1,baselineVersion='v1',calibrationGroupVersion='cal-0',scheduleVerified=True,capturedAt=capture.isoformat(),startTime=start.isoformat(),observedPlatform='Sleeper',observedPlatformLine=.5,observedAt=(capture-timedelta(seconds=10)).isoformat(),observedEventId=str(game),gradedAt=(start+timedelta(hours=3)).isoformat(),actual=outcome,outcome=outcome,resultStatus='GRADED',platformEligible=False))
    def candidate(self):
        start=self.now+timedelta(hours=1)
        return dict(self.rows[0],id='future',capturedAt=self.now.isoformat(),observedAt=self.now.isoformat(),startTime=start.isoformat(),resultStatus='PENDING',actionable=False)
    def test_only_observed_prospective_exact_line_evidence_promotes(self):
        evidence=report(self.rows,self.now);self.assertEqual(evidence['sports']['NHL']['eligibleTargets'],1)
        current=self.candidate();self.assertEqual(apply([current],evidence,self.now),1);self.assertTrue(current['platformEligible']);self.assertFalse(current['actionable'])
        for change in [dict(modelLine=1.5,observedPlatformLine=1.5),dict(baselineVersion='v2'),dict(calibrationGroupVersion='cal-1'),dict(observedAt=(self.now-timedelta(minutes=16)).isoformat())]:
            r=dict(current,**change);self.assertEqual(apply([r],evidence,self.now),0);self.assertFalse(r['platformEligible'])
    def test_unobserved_targets_and_invalid_timestamps_do_not_count(self):
        for change in [dict(forecastKind='MODEL_TEST'),dict(observedAt='invalid'),dict(observedPlatformLine=1.5),dict(observedAt='2020-01-01T00:00:00Z')]:
            evidence=report([dict(r,**change) for r in self.rows],self.now)
            self.assertEqual(evidence['sports']['NHL']['eligibleTargets'],0);self.assertEqual(evidence['sports']['NHL']['recorded'],0)
    def test_pending_future_duplicate_and_insufficient_support_never_promote(self):
        duplicate=report(self.rows+self.rows,self.now);self.assertEqual(duplicate['sports']['NHL']['recorded'],1000)
        for rows in [self.rows[:100],[dict(r,resultStatus='PENDING') for r in self.rows],[dict(r,gradedAt=(self.now+timedelta(hours=1)).isoformat()) for r in self.rows]]:
            self.assertEqual(report(rows,self.now)['sports']['NHL']['eligibleTargets'],0)
    def test_failed_skill_or_calibration_revokes_without_rewriting_frozen_history(self):
        poor=[dict(r,probability=.99) for r in self.rows]
        evidence=report(poor,self.now);self.assertEqual(evidence['sports']['NHL']['eligibleTargets'],0)
        current=dict(self.candidate(),platformEligible=True);apply([current],evidence,self.now);self.assertFalse(current['platformEligible'])
        self.assertEqual(self.rows[0]['probability'],.1);self.assertFalse(self.rows[0]['platformEligible'])

if __name__=='__main__':unittest.main()
