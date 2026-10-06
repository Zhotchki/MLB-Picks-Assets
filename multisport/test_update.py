import unittest
from datetime import date
from update import number, prob, actual, learn, corrected
class SecretFreeTests(unittest.TestCase):
    def setUp(self):
        from unittest.mock import patch
        # Integration fixtures must never consume a real provider key or credits.
        key=patch.dict('os.environ',{'PARLAY_API_KEY':''})
        key.start();self.addCleanup(key.stop)

class AdapterTests(SecretFreeTests):

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

class PipelineTests(SecretFreeTests):
    def test_pregame_capture_is_immutable_and_final_result_is_graded(self):
        import update, tempfile, json, io
        from pathlib import Path
        from datetime import datetime, timezone
        from unittest.mock import patch
        from contextlib import redirect_stdout
        class Clock(datetime):
            instant = datetime(2030,1,1,14,tzinfo=timezone.utc)
            @classmethod
            def now(cls, tz=None): return cls.instant.astimezone(tz) if tz else cls.instant
        state={'p':.8,'final':False}
        event={'gamePk':10,'gameDate':'2030-01-01T16:00:00Z','status':{'abstractGameState':'Preview','codedGameState':'P'},'teams':{'home':{'team':{'id':1}},'away':{'team':{'id':2}}}}
        def mock_get(url):
            if 'api=mobile' in url:
                return {'generatedAt':Clock.instant.isoformat(),'lastRefresh':Clock.instant.astimezone(update.ZoneInfo('America/Chicago')).strftime('%m/%d/%Y %I:%M:%S %p'),'picks':[{'Player':'Test Player','Team':'AA','Opponent':'BB','Prop':'Hits','Direction':'MORE','Probability':state['p'],'Probability Threshold':1,'Probability Samples':100,'Model Projection':1.5,'Injury Status':'ACTIVE'}]}
            if 'schedule?' in url:
                g=dict(event,status={'abstractGameState':'Final' if state['final'] else 'Preview','codedGameState':'F' if state['final'] else 'P'})
                return {'dates':[{'games':[g]}]}
            if 'teams?' in url:return {'teams':[{'id':1,'abbreviation':'AA','name':'Team A'},{'id':2,'abbreviation':'BB','name':'Team B'}]}
            if 'boxscore' in url:return {'teams':{'home':{'players':{'ID99':{'person':{'id':99,'fullName':'Test Player'},'stats':{'batting':{'plateAppearances':4,'hits':2}}}}},'away':{'players':{}}}}
            raise AssertionError(url)
        with tempfile.TemporaryDirectory() as tmp, patch.object(update,'ROOT',Path(tmp)),patch.object(update,'datetime',Clock),patch.object(update,'get',mock_get),redirect_stdout(io.StringIO()),patch('nfl_adapter.collect',return_value=([],{'status':'NOT_CONNECTED'},{})),patch('nfl_adapter.grade'),patch('nhl_adapter.collect',return_value=([],{'status':'NOT_CONNECTED'},{})),patch('nhl_adapter.grade'),patch('nba_adapter.collect',return_value=([],{'status':'NOT_CONNECTED'},{})),patch('nba_adapter.grade'):
            update.run()
            first=json.loads((Path(tmp)/'ledger.json').read_text())
            self.assertEqual(len(first),1); self.assertEqual(first[0]['probability'],.8)
            state['p']=.6; Clock.instant=datetime(2030,1,1,14,15,tzinfo=timezone.utc)
            update.run()
            saved=json.loads((Path(tmp)/'ledger.json').read_text())
            self.assertEqual(len(saved),1); self.assertEqual(saved[0]['probability'],.8)
            self.assertEqual(saved[0]['capturedAt'],first[0]['capturedAt'])
            state['final']=True; Clock.instant=datetime(2030,1,1,19,tzinfo=timezone.utc)
            update.run()
            graded=json.loads((Path(tmp)/'ledger.json').read_text())[0]
            self.assertEqual(graded['resultStatus'],'GRADED');self.assertEqual(graded['outcome'],1)
            self.assertEqual(graded['actual'],2);self.assertEqual(graded['probability'],.8)

class OutageTests(SecretFreeTests):

    def test_slow_import_cannot_backdate_forecast_after_kickoff(self):
        import update, tempfile, json, io
        from pathlib import Path
        from datetime import datetime, timezone
        from unittest.mock import patch
        from contextlib import redirect_stdout
        class Clock(datetime):
            calls=0
            @classmethod
            def now(cls,tz=None):
                cls.calls+=1
                return datetime(2030,1,1,14,0 if cls.calls==1 else 10,tzinfo=timezone.utc)
        row={'id':'NFL:late','sport':'NFL','probability':.8,'startTime':'2030-01-01T14:05:00Z'}
        with tempfile.TemporaryDirectory() as tmp, patch.object(update,'ROOT',Path(tmp)),patch.object(update,'datetime',Clock),patch.object(update,'collect_mlb',return_value=([],{'sourceStatus':'CURRENT'}, {},None,None)),patch.object(update,'grade_mlb'),patch('nfl_adapter.collect',return_value=([row],{'sourceStatus':'CURRENT'},{})),patch('nfl_adapter.grade'),patch('nhl_adapter.collect',return_value=([],{'sourceStatus':'CURRENT'},{})),patch('nhl_adapter.grade'),patch('nba_adapter.collect',return_value=([],{'sourceStatus':'CURRENT'},{})),patch('nba_adapter.grade'),redirect_stdout(io.StringIO()):
            update.run()
            data=json.loads((Path(tmp)/'data.json').read_text())
            self.assertFalse(data['picks']);self.assertEqual(data['results']['recorded'],0)
            self.assertEqual(data['rejected']['started_during_refresh'],1)

    def test_mlb_outage_keeps_nfl_forecasts_and_existing_ledger(self):
        import update, tempfile, json, io
        from pathlib import Path
        from datetime import datetime, timezone
        from unittest.mock import patch
        from contextlib import redirect_stdout
        row={'id':'NFL:test','sport':'NFL','gameId':'test','playerId':'99','player':'Test',
             'prop':'Rush Yards','direction':'MORE','target':50,'probability':.7,
             'startTime':'2099-01-01T12:00:00Z','resultStatus':'PENDING'}
        old={'id':'MLB:old','sport':'MLB','resultStatus':'PENDING','startTime':'2020-01-01T12:00:00Z','gameId':10}
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); (root/'ledger.json').write_text(json.dumps([old]))
            with patch.object(update,'ROOT',root), patch.object(update,'get',side_effect=TimeoutError), patch('nfl_adapter.collect',return_value=([row],{'status':'LIVE_FORECASTS','sourceStatus':'CURRENT','verifiedRows':1},{})),patch('nfl_adapter.grade'),patch('nhl_adapter.collect',return_value=([],{'status':'NOT_CONNECTED'},{})),patch('nhl_adapter.grade'),patch('nba_adapter.collect',return_value=([],{'status':'NOT_CONNECTED'},{})),patch('nba_adapter.grade'),redirect_stdout(io.StringIO()):
                update.run()
            data=json.loads((root/'data.json').read_text()); ledger=json.loads((root/'ledger.json').read_text())
            self.assertEqual(data['sports']['MLB']['sourceStatus'],'UNAVAILABLE')
            self.assertEqual(data['sports']['NFL']['sourceStatus'],'CURRENT')
            self.assertEqual(data['picks'],[row]); self.assertEqual(ledger,[old,row])
            self.assertEqual(data['sports']['MLB']['gradingStatus'],'AWAITING_RESULT_SOURCE')

if __name__=='__main__': unittest.main()
