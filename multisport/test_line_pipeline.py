import math,tempfile,unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from line_pipeline import collect,observed_valid
from update import norm
from platform_feed import match,SPORTS

class ObservedLinesTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2030,10,10,14,tzinfo=timezone.utc)
        self.base=dict(id='base',sport='NHL',gameId=1,playerId=99,player='Fixture Player',team='AAA',opponent='BBB',homeTeam='Team A',awayTeam='Team B',prop='Shots on Goal',direction='MORE',target=1,modelLine=.5,probability=.9,sourceProbability=.9,projection=3,distributionModel='COUNT_NB_V1',distributionShape=None,scheduleVerified=True,officialGameDate='2030-10-10',startTime='2030-10-10T20:00:00Z',capturedAt=self.now.isoformat(),season=20302031,platformEligible=False,baselineVersion='nb-1')
        self.line=dict(bookmaker='sleeper',sport_key=SPORTS['NHL'],player='Fixture Player',market_key='player_shots',line=2.5,home_team='Team A',away_team='Team B',commence_time=None,commence_time_reported=False,game_date='2030-10-10',canonical_event_id='event',age_seconds=10,period='FULL',odds_type='standard')
    def collect(self,base=None,line=None,age=0,fetch=None):
        r=base or self.base;board={'eligibleSports':[r['sport']],'sports':{r['sport']:{'fetchedAtEpoch':self.now.timestamp()-age,'rows':[line or self.line]}}}
        with tempfile.TemporaryDirectory() as tmp:
            return collect([r],board,self.now,Path(tmp),norm,fetch or (lambda url: (_ for _ in ()).throw(AssertionError('Unexpected network')))),board
    def test_actual_nhl_threshold_is_frozen_without_enabling_offer(self):
        (rows,reasons),board=self.collect();self.assertEqual(len(rows),1)
        r=rows[0];self.assertAlmostEqual(r['probability'],1-math.exp(-3)*(1+3+4.5))
        self.assertEqual(r['modelLine'],2.5);self.assertEqual(r['target'],3)
        self.assertTrue(observed_valid(r));self.assertFalse(r['actionable']);self.assertFalse(r['platformEligible'])
        self.assertIsNone(r['platform']);self.assertFalse(match(rows,board,self.now,norm)[0]);self.assertEqual(self.base['modelLine'],.5)
        self.assertFalse(observed_valid(r,self.now+timedelta(minutes=16)))
    def test_nba_mapping_and_same_line_existing_model_are_supported(self):
        base=dict(self.base,sport='NBA',prop='Rebounds');line=dict(self.line,sport_key=SPORTS['NBA'],market_key='player_rebounds')
        (rows,_),_=self.collect(base,line);self.assertEqual(rows[0]['sport'],'NBA')
        (rows,_),_=self.collect(line=dict(self.line,line=.5));self.assertEqual(rows[0]['probability'],.9)
    def test_stale_started_integer_special_and_wrong_fixture_cannot_be_frozen(self):
        self.assertFalse(self.collect(age=901)[0][0])
        for change in [dict(line=2),dict(odds_type='boosted'),dict(game_date='2030-10-11'),dict(away_team='Wrong'),dict(period='1H'),dict(age_seconds=901),dict(canonical_event_id=None)]:
            self.assertFalse(self.collect(line=dict(self.line,**change))[0][0])
        self.assertFalse(self.collect(base=dict(self.base,startTime=self.now.isoformat()))[0][0])
    def test_new_nfl_line_has_to_come_from_exact_probability_collector(self):
        base=dict(self.base,sport='NFL',team='GB',opponent='CHI',homeTeamAbbr='GB',awayTeamAbbr='CHI',prop='Receptions',distributionModel=None)
        line=dict(self.line,sport_key=SPORTS['NFL'],market_key='player_receptions',home_team='Green Bay Packers',away_team='Chicago Bears')
        self.assertFalse(self.collect(base,line)[0][0])
        (rows,_),_=self.collect(dict(base,modelLine=2.5,target=3),line);self.assertEqual(len(rows),1)
    def test_mlb_history_uses_real_supported_distinct_pregame_games(self):
        base=dict(self.base,sport='MLB',prop='Hits',teamId=7);line=dict(self.line,sport_key=SPORTS['MLB'],market_key='player_hits',line=1.5)
        splits=[dict(date=(self.now-timedelta(days=i+1)).date().isoformat(),game=dict(gamePk=i+1),gameType='R',team=dict(id=7),stat=dict(hits=i%3,plateAppearances=4)) for i in range(30)]
        def fetch(url):return {'stats':[{'splits':splits if '2030' in url else []}]}
        (rows,_),_=self.collect(base,line,fetch=fetch);self.assertEqual(rows[0]['samples'],30);self.assertEqual(rows[0]['baselineVersion'],'mlb-exact-line-empirical-v1')
        self.assertAlmostEqual(rows[0]['probability'],11/32)
        splits[:]=splits[:10]*3;self.assertFalse(self.collect(base,line,fetch=fetch)[0][0])
        self.assertFalse(self.collect(base,line,fetch=lambda url: (_ for _ in ()).throw(OSError()))[0][0])

class PipelineIntegrationTests(unittest.TestCase):
    def test_refresh_freezes_observed_lines_without_exposing_them_as_live_or_overwriting_them(self):
        import update,json,io
        from contextlib import redirect_stdout
        fixture=ObservedLinesTests();fixture.setUp();now=fixture.now
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):return now
        status={'sourceStatus':'CURRENT','status':'BASELINE_FORECASTS'}
        board={'status':'CONFIGURED','eligibleSports':['NHL'],'sports':{'NHL':{'fetchedAtEpoch':now.timestamp(),'rows':[fixture.line]}}}
        with tempfile.TemporaryDirectory() as tmp,patch.object(update,'ROOT',Path(tmp)),patch.object(update,'datetime',Clock),patch.object(update,'collect_mlb',return_value=([],status,{},None,None)),patch.object(update,'grade_mlb'),patch('nfl_adapter.collect',return_value=([],status,{})),patch('nfl_adapter.grade'),patch('nhl_adapter.collect',return_value=([fixture.base],status,{})),patch('nhl_adapter.grade'),patch('nba_adapter.collect',return_value=([],status,{})),patch('nba_adapter.grade'),patch('platform_feed.fetch',return_value=(board,{})),redirect_stdout(io.StringIO()):
            update.run();data=json.loads((Path(tmp)/'data.json').read_text());ledger=json.loads((Path(tmp)/'ledger.json').read_text())
            self.assertEqual(len(ledger),2);self.assertEqual(len(data['picks']),1);self.assertEqual(len(data['lineForecasts']),1);self.assertFalse(data['offers']);self.assertIn('nhlCalibration',data)
            self.assertEqual(data['lineValidation']['sports']['NHL']['recorded'],1);self.assertEqual(data['lineValidation']['sports']['NHL']['eligibleTargets'],0)
            frozen=next(r for r in ledger if r.get('forecastKind')=='SLEEPER_LINE')
            fixture.base['projection']=1;update.run()
            again=json.loads((Path(tmp)/'ledger.json').read_text())
            self.assertEqual(next(r for r in again if r['id']==frozen['id']),frozen)

if __name__=='__main__':unittest.main()
