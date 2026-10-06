import unittest,tempfile,math
from pathlib import Path
from datetime import datetime,timedelta,timezone
from nhl_adapter import collect,grade,history,baseline,exceedance,minutes,cached
from update import norm,corrected

NOW=datetime(2026,10,6,2,tzinfo=timezone.utc)
SEASON=20262027
TEAM={'id':10,'abbrev':'TOR','placeName':{'default':'Toronto'},'commonName':{'default':'Maple Leafs'}}
OTHER={'id':18,'abbrev':'NSH','placeName':{'default':'Nashville'},'commonName':{'default':'Predators'}}
GAME={'id':2026020044,'season':SEASON,'gameType':2,'gameState':'FUT','gameScheduleState':'OK',
      'startTimeUTC':'2026-10-06T23:00:00Z','homeTeam':TEAM,'awayTeam':OTHER}
PLAYER={'id':99,'firstName':{'default':'Test'},'lastName':{'default':'Player'}}

def log(season,days):
    return {'seasonId':season,'gameTypeId':2,'gameLog':[{'gameId':int(season)*100+i,'teamAbbrev':'TOR',
            'gameDate':day,'shots':3,'toi':'20:00'} for i,day in enumerate(days)]}

class NHLTests(unittest.TestCase):
    def fixture(self):
        current=log(SEASON,['2026-10-03','2026-09-30','2026-09-29'])
        prior=log(SEASON-10001,[(datetime(2026,4,1)-timedelta(days=i)).date().isoformat() for i in range(30)])
        injuries={'status':'success','timestamp':NOW.isoformat(),'injuries':[]}
        def fetch(url):
            if '/schedule/' in url:return {'gameWeek':[{'games':[GAME]}]}
            if url.endswith('/injuries'):return injuries
            if '/roster/' in url:return {'forwards':[PLAYER] if '/TOR/' in url else [],'defensemen':[]}
            if '/club-stats/' in url:return {'season':str(SEASON),'gameType':2,'skaters':[{'playerId':99,'gamesPlayed':3,'shots':9}]}
            if f'/game-log/{SEASON}/' in url:return current
            if f'/game-log/{SEASON-10001}/' in url:return prior
            raise AssertionError(url)
        return current,prior,injuries,fetch

    def test_collection_verifies_identity_time_and_baseline_status(self):
        *_,fetch=self.fixture()
        with tempfile.TemporaryDirectory() as tmp:
            rows,status,rejected=collect(NOW,Path(tmp),{'version':'baseline'},corrected,norm,fetch)
        self.assertEqual(len(rows),5);self.assertEqual(status['verifiedRows'],5)
        self.assertEqual(rows[0]['playerId'],99);self.assertEqual(rows[0]['expectedPlayingTime'],20)
        self.assertEqual(rows[0]['samples'],33)
        self.assertTrue(all(r['platformEligible'] is False and r['probabilityStatus']=='UNVALIDATED_BASELINE' for r in rows))
        self.assertGreater(rows[0]['probability'],rows[-1]['probability'])

    def test_any_listed_injury_excluded(self):
        cur,old,injuries,fetch=self.fixture()
        injuries['injuries']=[{'displayName':'Toronto Maple Leafs','injuries':[{'athlete':{'displayName':'Test Player'},'status':'Day-To-Day'}]}]
        with tempfile.TemporaryDirectory() as tmp:
            rows,_,reject=collect(NOW,Path(tmp),{'version':'baseline'},corrected,norm,fetch)
        self.assertFalse(rows);self.assertEqual(reject['injury_report'],1)

    def test_stale_injury_report_stops_forecasts(self):
        _,_,injuries,fetch=self.fixture();injuries['timestamp']='2026-10-01T00:00:00Z'
        with tempfile.TemporaryDirectory() as tmp,self.assertRaises(ValueError):
            collect(NOW,Path(tmp),{'version':'baseline'},corrected,norm,fetch)

    def test_started_and_preseason_games_excluded(self):
        *_,fetch=self.fixture()
        for game in (dict(GAME,gameType=1),dict(GAME,startTimeUTC='2026-10-06T01:00:00Z')):
            def replaced(url):
                return {'gameWeek':[{'games':[game]}]} if '/schedule/' in url else fetch(url)
            with tempfile.TemporaryDirectory() as tmp:
                rows,status,_=collect(NOW,Path(tmp),{'version':'baseline'},corrected,norm,replaced)
            self.assertFalse(rows);self.assertEqual(status['gamesChecked'],0)

    def test_history_excludes_wrong_team_future_and_wrong_season(self):
        cur,_,_,_=self.fixture();cur['gameLog'] += [dict(cur['gameLog'][0],gameId=7,teamAbbrev='BOS'),dict(cur['gameLog'][0],gameId=8,gameDate='2026-10-10')]
        self.assertEqual(len(history(cur,SEASON,'TOR',NOW.date())),3)
        self.assertFalse(history(cur,SEASON-10001,'TOR',NOW.date()))

    def test_ice_time_affects_projection_and_role_change_is_excluded(self):
        cur,old,_,_=self.fixture();a=history(cur,SEASON,'TOR',NOW.date());b=history(old,SEASON-10001,'TOR',NOW.date())
        first,_=baseline(a,b,NOW)
        reduced=[dict(r,minutes=16) for r in a];second,reason=baseline(reduced,b,NOW)
        self.assertIsNone(reason);self.assertLess(second['projection'],first['projection'])
        self.assertEqual(baseline([dict(r,minutes=12) for r in a],b,NOW)[1],'uncertain_ice_time')
        self.assertEqual(baseline(a,[],NOW)[1],'insufficient_history')

    def test_distribution_agrees_with_poisson_and_is_monotone(self):
        self.assertAlmostEqual(exceedance(3,None,1),1-math.exp(-3))
        self.assertGreater(exceedance(3,2,1),exceedance(3,2,5))
        self.assertIsNone(minutes('12:99'));self.assertIsNone(minutes(None))

    def test_final_zero_is_loss_missing_row_pending_and_no_toi_void(self):
        for player,expected in (({'playerId':99,'sog':0,'toi':'20:00'},'GRADED'),(None,'PENDING'),({'playerId':99,'sog':0,'toi':'0:00'},'VOID')):
            row={'sport':'NHL','season':SEASON,'gameId':GAME['id'],'playerId':99,'team':'TOR','opponent':'NSH','target':1,'startTime':'2026-10-01T00:00:00Z','resultStatus':'PENDING'}
            box={'id':GAME['id'],'season':SEASON,'gameType':2,'gameState':'OFF','homeTeam':TEAM,'awayTeam':OTHER,
                 'playerByGameStats':{'homeTeam':{'forwards':[player] if player else []}}}
            with tempfile.TemporaryDirectory() as tmp:grade([row],NOW,Path(tmp),lambda _:box)
            self.assertEqual(row['resultStatus'],expected)
            if expected=='GRADED':self.assertEqual(row['outcome'],0)

    def test_expired_cache_does_not_hide_network_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            cached(tmp,'example','url',900,NOW,lambda _:{'value':1})
            def fail(_):raise TimeoutError()
            with self.assertRaises(TimeoutError):cached(tmp,'example','url',900,NOW+timedelta(minutes=16),fail)

if __name__=='__main__':unittest.main()
