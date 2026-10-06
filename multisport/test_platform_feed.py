import unittest,os,tempfile,json
from urllib.error import HTTPError
from pathlib import Path
from datetime import datetime,timezone
from unittest.mock import patch
from platform_feed import fetch,match,slips
from update import norm
class PlatformTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2030,1,1,14,tzinfo=timezone.utc)
        self.forecast={'sport':'MLB','gameId':1,'playerId':99,'player':'Fixture Player','team':'AA','opponent':'BB','homeTeam':'Team A','awayTeam':'Team B','prop':'Hits','direction':'MORE','target':2,'probability':.7,'startTime':'2030-01-01T16:00:00Z'}
        self.row={'bookmaker':'sleeper','player':'Fixture Player','market_key':'player_hits','line':1.5,'home_team':'Team A','away_team':'Team B','commence_time':'2030-01-01T16:00:00Z','commence_time_reported':True,'canonical_event_id':'abc','age_seconds':3,'period':'FULL','odds_type':'standard'}
    def scheduled(self):
        self.forecast.update(scheduleVerified=True,officialGameDate='2030-01-01')
        self.row.update(commence_time=None,commence_time_reported=False,game_date='2030-01-01',is_dfs_flat_payout=True)
        self.row.pop('odds_type')
    def board(self):return {'sports':{'MLB':{'fetchedAtEpoch':self.now.timestamp(),'rows':[self.row]}}}
    def test_missing_key_makes_no_request(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'PARLAY_API_KEY':''}),patch('urllib.request.urlopen') as request:
            board,state=fetch(Path(tmp),self.now);self.assertEqual(board['status'],'NEEDS_API_KEY');request.assert_not_called()
    def test_http_errors_report_safe_status_and_retry_after_15_minutes(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'PARLAY_API_KEY':'private-test-key'}),patch('urllib.request.urlopen',side_effect=HTTPError('secret-url',403,'secret-message',{},None)) as request:
            board,state=fetch(Path(tmp),self.now)
            self.assertEqual(request.call_count,4)
            self.assertEqual(state['sports']['MLB']['errorCode'],'HTTP_403')
            self.assertNotIn('secret',json.dumps(state))
            Path(tmp,'feed-state.json').write_text(json.dumps(state))
            fetch(Path(tmp),self.now);self.assertEqual(request.call_count,4)
            from datetime import timedelta
            fetch(Path(tmp),self.now+timedelta(minutes=15));self.assertEqual(request.call_count,8)
    def test_successful_board_keeps_12_hour_budget_interval(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'PARLAY_API_KEY':'private-test-key'}),patch('urllib.request.urlopen') as request:
            state={'month':'2030-01','creditsUsed':12,'sports':{s:{'status':'OBSERVED_BOARD','rows':[],'fetchedAtEpoch':self.now.timestamp()-3600} for s in ['MLB','NFL','NBA','NHL']}}
            Path(tmp,'feed-state.json').write_text(json.dumps(state))
            fetch(Path(tmp),self.now);request.assert_not_called()
    def test_only_exact_line_gets_probability(self):
        rows,_=match([self.forecast],self.board(),self.now,norm);self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['payoutMultiplier'])
        self.row['line']=2.5;rows,_=match([self.forecast],self.board(),self.now,norm);self.assertEqual(rows,[])
    def test_unknown_period_is_rejected(self):
        self.row['period']='UNKNOWN';self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
    def test_wrong_game_cannot_match_name(self):
        self.row['away_team']='Team C';self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
    def test_stale_offer_rejected(self):
        self.row['age_seconds']=901;self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
    def test_unvalidated_baseline_never_enters_playable_offers(self):
        self.forecast['platformEligible']=False
        self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
    def test_duplicate_player_or_event_not_in_slip(self):
        a=dict(self.forecast,actionable=True,platform='Sleeper');b=dict(a,prop='Runs');c=dict(a,playerId=100)
        self.assertEqual(slips([a,b,c],2),[])
        d=dict(a,playerId=101,gameId=2,probability=.6)
        result=slips([a,b,c,d],2);self.assertTrue(result);self.assertAlmostEqual(result[0]['probability'],.42)
        self.assertEqual(len({r['playerId'] for r in result[0]['legs']}),2)
    def test_missing_kickoff_resolves_unique_official_fixture_and_flags_unknown_type(self):
        self.scheduled()
        rows,_=match([self.forecast],self.board(),self.now,norm)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['kickoffSource'],'OFFICIAL_SCHEDULE')
        self.assertTrue(rows[0]['requiresPlatformReview'])
        self.assertEqual(rows[0]['platformOfferType'],'unreported')
        self.assertIsNone(rows[0]['payoutMultiplier'])
    def test_ambiguous_fixture_cannot_be_resolved(self):
        self.scheduled()
        other=dict(self.forecast,gameId=2,startTime='2030-01-01T19:00:00Z')
        self.assertEqual(match([self.forecast,other],self.board(),self.now,norm)[0],[])
    def test_missing_date_unverified_schedule_and_wrong_date_are_rejected(self):
        self.scheduled()
        for value in (None,'2030-01-02'):
            self.row['game_date']=value
            self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
        self.row['game_date']='2030-01-01';self.forecast['scheduleVerified']=False
        self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
    def test_reversed_home_and_away_do_not_resolve(self):
        self.scheduled();self.row.update(home_team='Team B',away_team='Team A')
        self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
    def test_explicit_special_type_is_excluded_even_with_other_standard_tag(self):
        for tag in ('demon','boosted','goblin',None):
            self.row['projection_type']=tag
            self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
    def test_unknown_type_requires_explicit_dfs_evidence(self):
        self.row.pop('odds_type')
        self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
        self.row['is_dfs_flat_payout']=True
        self.assertTrue(match([self.forecast],self.board(),self.now,norm)[0][0]['requiresPlatformReview'])
    def test_started_official_fixture_and_conflicting_timestamp_are_excluded(self):
        self.scheduled();self.forecast['startTime']='2030-01-01T13:00:00Z'
        self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
        self.forecast['startTime']='2030-01-01T16:00:00Z';self.row['commence_time']='2030-01-01T16:00:00Z'
        self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
    def test_provider_market_alias_preserves_exact_line(self):
        self.forecast['prop']='Walks';self.row['market_key']='player_bat_walks'
        self.assertEqual(len(match([self.forecast],self.board(),self.now,norm)[0]),1)
        self.row['line']=2.5
        self.assertEqual(match([self.forecast],self.board(),self.now,norm)[0],[])
    def test_nfl_official_home_away_and_dated_fixture(self):
        self.scheduled()
        self.forecast.update(sport='NFL',prop='Rush Yards',team='GB',opponent='CHI',homeTeamAbbr='GB',awayTeamAbbr='CHI')
        self.row.update(market_key='player_rushing_yards',home_team='Green Bay Packers',away_team='Chicago Bears')
        board={'sports':{'NFL':{'fetchedAtEpoch':self.now.timestamp(),'rows':[self.row]}}}
        self.assertEqual(len(match([self.forecast],board,self.now,norm)[0]),1)
    def response(self,headers=None):
        import io
        response=io.StringIO('[]');response.headers=headers or {};return response
    def test_eligible_sports_share_budget_and_other_sports_are_not_polled(self):
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'PARLAY_API_KEY':'fixture-key'}),patch('urllib.request.urlopen',side_effect=lambda *a,**k:self.response()) as request:
            board,state=fetch(Path(tmp),self.now,{'MLB','NFL'})
            self.assertEqual(request.call_count,2);self.assertEqual(board['refreshMinutes'],360)
            self.assertEqual(board['eligibleSports'],['MLB','NFL'])
            self.assertTrue(all('/baseball_mlb/' in call.args[0].full_url or '/americanfootball_nfl/' in call.args[0].full_url for call in request.call_args_list))
            Path(tmp,'feed-state.json').write_text(json.dumps(state))
            board,state=fetch(Path(tmp),self.now+timedelta(hours=3),{'MLB','NFL'})
            self.assertEqual(request.call_count,2)
            Path(tmp,'feed-state.json').write_text(json.dumps(state))
            fetch(Path(tmp),self.now+timedelta(hours=6),{'MLB','NFL'})
            self.assertEqual(request.call_count,4)
    def test_no_eligible_sports_never_spends_credits(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'PARLAY_API_KEY':'fixture-key'}),patch('urllib.request.urlopen') as request:
            board,state=fetch(Path(tmp),self.now,set())
            request.assert_not_called();self.assertEqual(state['creditsUsed'],0)
            self.assertIsNone(board['nextRefreshAt'])
    def test_daily_cap_includes_failures_and_resumes_next_utc_day(self):
        from datetime import timedelta
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'PARLAY_API_KEY':'fixture-key','PARLAY_DAILY_CREDIT_CAP':'6'}),patch('urllib.request.urlopen',side_effect=HTTPError('private',401,'private',{},None)) as request:
            board,state=fetch(Path(tmp),self.now,{'MLB','NFL'})
            self.assertEqual(request.call_count,2)
            Path(tmp,'feed-state.json').write_text(json.dumps(state))
            board,state=fetch(Path(tmp),self.now+timedelta(minutes=15),{'MLB','NFL'})
            self.assertEqual(request.call_count,2);self.assertEqual(board['refreshReason'],'DAILY_BUDGET')
            self.assertEqual(board['nextRefreshAt'],'2030-01-02T00:00:00+00:00')
            Path(tmp,'feed-state.json').write_text(json.dumps(state))
            board,state=fetch(Path(tmp),self.now+timedelta(days=1),{'MLB','NFL'})
            self.assertEqual(request.call_count,4);self.assertEqual(state['creditsUsed'],12)
            self.assertEqual(state['dailyCreditsUsed'],6)
    def test_reported_provider_usage_prevents_untracked_usage_overspend(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'PARLAY_API_KEY':'fixture-key'}),patch('urllib.request.urlopen',side_effect=lambda *a,**k:self.response({'x-requests-used':'899','x-requests-remaining':'1'})) as request:
            board,state=fetch(Path(tmp),self.now,{'MLB','NFL'})
            self.assertEqual(request.call_count,1)
            self.assertEqual(state['creditsUsed'],899);self.assertEqual(board['refreshReason'],'MONTHLY_BUDGET')
            self.assertEqual(board['nextRefreshAt'],'2030-02-01T00:00:00+00:00')
    def test_default_single_sport_has_at_most_eight_calls_per_day(self):
        from datetime import timedelta
        start=self.now.replace(hour=0)
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{'PARLAY_API_KEY':'fixture-key'}),patch('urllib.request.urlopen',side_effect=lambda *a,**k:self.response()) as request:
            for hour in range(24):
                board,state=fetch(Path(tmp),start+timedelta(hours=hour),{'MLB'})
                Path(tmp,'feed-state.json').write_text(json.dumps(state))
            self.assertEqual(request.call_count,8)
            self.assertEqual(state['creditsUsed'],24)
            self.assertEqual(board['refreshMinutes'],180)
if __name__=='__main__':unittest.main()
