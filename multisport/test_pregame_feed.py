import io,json,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from platform_feed import fetch,pregame_checks,match
from update import norm

class PregameTests(unittest.TestCase):
    def setUp(self):self.now=datetime(2030,1,1,8,tzinfo=timezone.utc)
    def rows(self,start=None):
        start=start or self.now.replace(hour=20)
        return [{'sport':'MLB','gameId':1,'startTime':start.isoformat(),'scheduleVerified':True,'platformEligible':True}]
    def response(self):
        r=io.StringIO('[]');r.headers={};return r
    def test_off_hours_use_no_requests_and_report_first_window(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'PARLAY_API_KEY':'fixture'},clear=True),patch('urllib.request.urlopen') as request:
            board,state=fetch(Path(tmp),self.now,{'MLB'},self.rows())
            request.assert_not_called();self.assertEqual(state['creditsUsed'],0)
            self.assertEqual(board['nextRefreshAt'],'2030-01-01T16:00:00+00:00')
            self.assertEqual(board['refreshMode'],'PREGAME_WINDOWS')
    def test_near_start_window_fetches_once_and_cannot_repeat(self):
        now=self.now.replace(hour=19,minute=45)
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'PARLAY_API_KEY':'fixture'},clear=True),patch('urllib.request.urlopen',side_effect=lambda *a,**kw:self.response()) as request:
            board,state=fetch(Path(tmp),now,{'MLB'},self.rows())
            self.assertEqual(request.call_count,1)
            Path(tmp,'feed-state.json').write_text(json.dumps(state))
            fetch(Path(tmp),now+timedelta(minutes=3),{'MLB'},self.rows())
            self.assertEqual(request.call_count,1)
    def test_missed_window_and_started_games_are_not_caught_up(self):
        for now in [self.now.replace(hour=18),self.now.replace(hour=19,minute=57),self.now.replace(hour=20,minute=1)]:
            with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'PARLAY_API_KEY':'fixture'},clear=True),patch('urllib.request.urlopen') as request:
                fetch(Path(tmp),now,{'MLB'},self.rows());request.assert_not_called()
    def test_same_sport_start_batches_games_and_targets_do_not_inflate_calls(self):
        rows=self.rows()*10+[dict(self.rows()[0],gameId=2)]
        checks=pregame_checks(rows,self.now)
        self.assertEqual(len(checks),3)
        self.assertTrue(all(len(slot['games'])==2 for slot in checks))
    def test_tight_remaining_budget_prefers_nearer_windows(self):
        checks=pregame_checks(self.rows(),self.now,remaining_today=2)
        self.assertEqual({slot['leadMinutes'] for slot in checks},{20,90})
        self.assertNotIn(240,[slot['leadMinutes'] for slot in checks])
    def test_plan_limits_each_utc_day_and_excludes_baselines_or_unverified_starts(self):
        rows=[dict(self.rows()[0],gameId=i,startTime=(self.now.replace(hour=12)+timedelta(hours=i)).isoformat()) for i in range(10)]
        rows += [dict(self.rows()[0],sport='NHL',platformEligible=False),dict(self.rows()[0],sport='NBA',scheduleVerified=False)]
        checks=pregame_checks(rows,self.now,daily_calls=4)
        dates={}
        for slot in checks:dates[slot['at'].date()]=dates.get(slot['at'].date(),0)+1
        self.assertTrue(all(n<=4 for n in dates.values()))
        self.assertTrue(all(slot['sport']=='MLB' for slot in checks))
    def test_explicit_interval_override_keeps_existing_mode(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict('os.environ',{'PARLAY_API_KEY':'fixture','PICKEM_REFRESH_MINUTES':'60'},clear=True),patch('urllib.request.urlopen',side_effect=lambda *a,**kw:self.response()) as request:
            board,state=fetch(Path(tmp),self.now,{'MLB'},self.rows())
            self.assertEqual(request.call_count,1);self.assertEqual(board['refreshMode'],'INTERVAL')
    def test_expired_and_ineligible_board_lines_have_distinct_reasons(self):
        board={'eligibleSports':['MLB'],'sports':{'MLB':{'fetchedAtEpoch':self.now.timestamp()-901,'rows':[{},{}]},'NHL':{'fetchedAtEpoch':self.now.timestamp(),'rows':[{}]}}}
        rows,counts=match([],board,self.now,norm)
        self.assertEqual(counts['observed'],3);self.assertEqual(counts['excluded'],{'expired_board':2,'sport_not_eligible':1})
        self.assertFalse(rows)

if __name__=='__main__':unittest.main()
