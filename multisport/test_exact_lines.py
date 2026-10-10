import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from pathlib import Path
from exact_lines import collect,VERSION
from update import norm
from platform_feed import match

class ExactLinesTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2030,10,10,14,tzinfo=timezone.utc)
        self.forecast=dict(sport='NFL',gameId='future',playerId='p1',player='Test Player',team='GB',opponent='CHI',homeTeamAbbr='GB',awayTeamAbbr='CHI',prop='Receptions',direction='MORE',target=4,modelLine=3.5,probability=.7,sourceProbability=.7,scheduleVerified=True,officialGameDate='2030-10-10',startTime='2030-10-10T20:00:00Z',season=2030,week=8,expectedPlayingTime=.8)
        self.line=dict(bookmaker='sleeper',sport_key='americanfootball_nfl',player='Test Player',market_key='player_receptions',line=5.5,home_team='Green Bay Packers',away_team='Chicago Bears',commence_time_reported=False,game_date='2030-10-10',canonical_event_id='event',age_seconds=1,period='FULL',is_dfs_flat_payout=True)
        self.board=dict(eligibleSports=['NFL'],sports={'NFL':dict(rows=[self.line],fetchedAtEpoch=self.now.timestamp())})
        self.games=[];self.stats=[]
        for i in range(8):
            date=(self.now-timedelta(days=7*i+1)).date().isoformat()
            gid='history'+str(i)
            self.games.append(dict(game_id=gid,season='2030',week=str(i+1),gameday=date,gametime='13:00',game_type='REG',home_team='GB',away_team='CHI',home_score='20',away_score='10'))
            self.stats.append(dict(player_id='p1',season='2030',week=str(i+1),season_type='REG',team='GB',opponent_team='CHI',game_id=gid,receptions=str(i)))
    def collect(self):
        def source(root,name,*args):
            if name=='nfl-schedule.csv':return self.games
            return self.stats if '2030' in name else []
        with patch('exact_lines.cache_read',side_effect=source):
            return collect([self.forecast],self.board,self.now,Path('/tmp'),norm)
    def test_exact_observed_line_probability_is_distinct_and_ineligible(self):
        rows,_=self.collect();self.assertEqual(len(rows),1)
        r=rows[0];self.assertEqual(r['modelLine'],5.5);self.assertEqual(r['samples'],8)
        self.assertAlmostEqual(r['probability'],.3);self.assertEqual(r['baselineVersion'],VERSION)
        self.assertFalse(r['platformEligible']);self.assertFalse(r['actionable'])
        self.assertEqual(match(rows,self.board,self.now,norm)[0],[])
        self.assertEqual(self.forecast['modelLine'],3.5)
    def test_stale_board_makes_no_history_requests(self):
        self.board['sports']['NFL']['fetchedAtEpoch']-=901
        with patch('exact_lines.cache_read') as read:
            self.assertEqual(collect([self.forecast],self.board,self.now,Path('/tmp'),norm)[0],[]);read.assert_not_called()
    def test_integer_lines_and_wrong_fixture_are_excluded(self):
        self.line['line']=5;self.assertEqual(self.collect()[0],[])
        self.line['line']=5.5;self.line['away_team']='Detroit Lions';self.assertEqual(self.collect()[0],[])
    def test_duplicate_history_does_not_inflate_support(self):
        self.stats=self.stats[:4]*3
        self.assertEqual(self.collect()[0],[])
    def test_future_or_wrong_team_history_does_not_count(self):
        self.stats[0]['team']='MIN';self.assertEqual(self.collect()[0],[])
        self.stats[0]['team']='GB';self.games[0]['gameday']='2030-10-11';self.assertEqual(self.collect()[0],[])
    def test_missing_stats_do_not_become_zero(self):
        self.stats[0].pop('receptions');self.assertEqual(self.collect()[0],[])
    def test_history_outage_is_isolated(self):
        with patch('exact_lines.cache_read',side_effect=OSError('unavailable')):
            rows,rejected=collect([self.forecast],self.board,self.now,Path('/tmp'),norm)
            self.assertFalse(rows);self.assertEqual(rejected['history_source_unavailable'],1)
    def test_existing_line_and_special_offer_are_excluded(self):
        self.line['line']=3.5;self.assertFalse(self.collect()[0])
        self.line['line']=5.5;self.line['odds_type']='boosted';self.assertFalse(self.collect()[0])
    def test_final_grade_and_validation_use_new_exact_threshold(self):
        import nfl_adapter,validation
        rows,_=self.collect();r=rows[0]
        game=dict(self.games[0],game_id='future',gameday='2030-10-10')
        stats=dict(self.stats[0],week='8',game_id='future',receptions='5')
        def source(root,name,*args):return [game] if name=='nfl-schedule.csv' else [stats]
        with patch('nfl_adapter.cache_read',side_effect=source):nfl_adapter.grade(rows,self.now+timedelta(days=1),Path('/tmp'))
        self.assertEqual(r['outcome'],0);self.assertTrue(validation.graded(r));self.assertEqual(r['probability'],.3)

if __name__=='__main__':unittest.main()
