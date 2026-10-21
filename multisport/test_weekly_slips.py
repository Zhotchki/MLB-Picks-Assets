import unittest
from datetime import datetime,timezone,timedelta
from weekly_slips import update,SIZES,week_key
from platform_feed import slip_sets

class WeeklySlipTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2030,1,2,14,tzinfo=timezone.utc)
        self.rows=[dict(id=f'NHL:{i}:MORE:1',sport='NHL',gameId=i,playerId=i,player=f'Player {i}',prop='Shots on Goal',direction='MORE',target=1,modelLine=.5,probability=.8+i*.001,sourceProbability=.8,platformEligible=False,probabilityStatus='UNVALIDATED_BASELINE',scheduleVerified=True,capturedAt=self.now.isoformat(),startTime=(self.now+timedelta(hours=i+1)).isoformat()) for i in range(16)]
        self.sports={'NHL':{'sourceStatus':'CURRENT'}}
    def run_update(self,saved=None,rows=None,ledger=None,now=None):return update(saved or [],self.rows if rows is None else rows,ledger or [],self.sports,now or self.now)
    def test_three_per_size_unique_players_events_and_not_platform_slips(self):
        saved,t=self.run_update();self.assertEqual(len(saved),18)
        for size in SIZES:self.assertEqual(sum(s['size']==size for s in saved),3)
        from collections import Counter
        from platform_feed import pick_key
        for size in SIZES:
            self.assertLessEqual(max(Counter(pick_key(r) for s in saved if s['size']==size for r in s['legs']).values()),2)
        for s in saved:
            self.assertEqual(len({r['gameId'] for r in s['legs']}),s['size']);self.assertEqual(len({r['playerId'] for r in s['legs']}),s['size'])
            self.assertFalse(s['actionable']);self.assertIsNone(s['platform'])
            self.assertEqual(slip_sets(s['legs'])['2'],[])
    def test_same_week_refresh_never_changes_frozen_picks_or_probabilities(self):
        saved,_=self.run_update();changed=[dict(r,probability=.1) for r in self.rows]
        again,_=self.run_update(saved,changed)
        self.assertEqual(saved,again)
    def test_started_stale_wrong_week_and_unverified_rows_cannot_be_captured(self):
        cases=[dict(startTime=self.now.isoformat()),dict(capturedAt=(self.now-timedelta(minutes=46)).isoformat()),dict(startTime=(self.now+timedelta(days=9)).isoformat()),dict(scheduleVerified=False)]
        for change in cases:self.assertFalse(self.run_update(rows=[dict(r,**change) for r in self.rows])[0])
    def test_partial_slots_wait_then_fill_without_duplicates(self):
        saved,_=self.run_update(rows=self.rows[:2]);self.assertEqual(len(saved),1)
        again,_=self.run_update(saved);self.assertEqual(len(again),18);self.assertEqual(again[0],saved[0])
    def test_all_hits_only_when_every_leg_resolves_hit(self):
        saved,_=self.run_update();s=saved[0]
        ledger=[dict(r,resultStatus='GRADED',actual=1,outcome=1,gradedAt=(self.now+timedelta(days=1)).isoformat()) for r in self.rows]
        pending,_=self.run_update([s],rows=[],ledger=ledger[:1]);self.assertFalse(pending[0]['allHit'])
        done,_=self.run_update([s],rows=[],ledger=ledger);self.assertTrue(done[0]['allHit']);self.assertEqual(done[0]['status'],'ALL_HIT')
        # Grades are terminal even if later source values change.
        frozen,_=self.run_update(done,rows=[],ledger=[dict(r,actual=0,outcome=0) for r in ledger]);self.assertEqual(done,frozen)
    def test_misses_voids_and_missing_or_invalid_results(self):
        saved,_=self.run_update();s=saved[0];ids={r['forecastId'] for r in s['legs']};r=next(r for r in self.rows if r['id'] in ids)
        ledger=[dict(x,resultStatus='GRADED',actual=1,outcome=1,gradedAt=(self.now+timedelta(days=1)).isoformat()) for x in self.rows]
        bad=[dict(x,actual=0,outcome=0) if x['id']==r['id'] else x for x in ledger]
        done,_=self.run_update([s],rows=[],ledger=bad);self.assertEqual(done[0]['status'],'MISSED');self.assertFalse(done[0]['allHit'])
        voids=[dict(x,resultStatus='VOID') if x['id']==r['id'] else x for x in ledger]
        done,_=self.run_update([s],rows=[],ledger=voids);self.assertEqual(done[0]['status'],'VOIDED');self.assertFalse(done[0]['allHit'])
        wrong=[dict(x,modelLine=9.5) for x in ledger]
        done,_=self.run_update([s],rows=[],ledger=wrong);self.assertEqual(done[0]['pending'],s['size'])
    def test_new_week_archives_and_never_backfills_after_kickoff(self):
        saved,_=self.run_update();now=self.now+timedelta(days=7)
        rows=[dict(r,id=r['id']+'new',capturedAt=now.isoformat(),startTime=(now+timedelta(hours=2)).isoformat()) for r in self.rows]
        again,t=self.run_update(saved,rows,now=now);self.assertEqual(len(again),36);self.assertEqual(again[:18],saved);self.assertNotEqual(t['currentWeek'],saved[0]['week'])
    def test_week_is_chicago_calendar_week(self):
        self.assertEqual(week_key(datetime(2030,1,7,2,tzinfo=timezone.utc)),'2030-W01')
    def test_outage_does_not_create_paper_slips(self):
        self.sports['NHL']['sourceStatus']='STALE';self.assertFalse(self.run_update()[0])

if __name__=='__main__':unittest.main()
