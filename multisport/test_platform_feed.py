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
if __name__=='__main__':unittest.main()
