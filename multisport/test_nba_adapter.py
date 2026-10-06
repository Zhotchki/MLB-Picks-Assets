import unittest,tempfile
from pathlib import Path
from datetime import datetime,timezone,timedelta
from nba_adapter import history,baseline,collect,grade,stat_value
from update import norm,corrected

NOW=datetime(2026,10,6,2,tzinfo=timezone.utc)
TEAM={'id':'13','abbreviation':'LAL','displayName':'Los Angeles Lakers'}
def log(season,days):
    events={str(season)+':'+str(i):{'gameDate':d,'homeTeamId':'13','awayTeamId':'25','gameResult':'W'} for i,d in enumerate(days)}
    rows=[{'eventId':str(season)+':'+str(i),'stats':['30','25','8','5','2-6']} for i in range(len(days))]
    return {'filters':[{'name':'season','value':str(season)}],
            'names':['minutes','points','totalRebounds','assists','threePointFieldGoalsMade-threePointFieldGoalsAttempted'],
            'events':events,'seasonTypes':[{'displayName':f'{season-1}-{str(season)[-2:]} Regular Season',
                                         'displayTeam':'LAL','categories':[{'events':rows}]}]}

class NBATests(unittest.TestCase):
    def fixture(self,injured=False,wrong_team=False):
        game={'id':'future','date':'2026-10-06T23:00Z','season':{'year':2027,'type':2},'status':{'type':{'state':'pre'}},
              'competitions':[{'competitors':[{'homeAway':'home','team':TEAM},{'homeAway':'away','team':{'id':'25','abbreviation':'OKC','displayName':'Oklahoma City Thunder'}}]}]}
        def fetch(url):
            if '/scoreboard?' in url:return {'events':[game]}
            if url.endswith('/injuries'):return {'status':'success','timestamp':NOW.isoformat(),'injuries':[{'id':'13','injuries':[{'athlete':{'displayName':'Test Player'}}]}] if injured else []}
            if '/roster' in url:
                tid='13' if '/13/' in url else '25'
                return {'team':{'id':'wrong' if wrong_team else tid},'season':{'year':2027},'athletes':[{'id':'99','displayName':'Test Player','status':{'type':'active'}}] if tid=='13' else []}
            if 'season=2027' in url:return log(2027,['2026-10-03T00:00:00Z','2026-10-01T00:00:00Z','2026-09-29T00:00:00Z'])
            if 'season=2026' in url:return log(2026,[(datetime(2026,4,1,tzinfo=timezone.utc)-timedelta(days=i)).isoformat() for i in range(30)])
            raise AssertionError(url)
        return fetch

    def test_complete_collection_preserves_baseline_gate_and_minutes(self):
        with tempfile.TemporaryDirectory() as tmp:rows,status,_=collect(NOW,Path(tmp),{'version':'base'},corrected,norm,self.fixture())
        self.assertEqual(len(rows),22);self.assertEqual(status['verifiedRows'],22)
        self.assertEqual(rows[0]['expectedPlayingTime'],30);self.assertEqual(rows[0]['samples'],33)
        self.assertTrue(all(r['platformEligible'] is False for r in rows))

    def test_injury_or_wrong_roster_identity_excludes_forecasts(self):
        for fetch in (self.fixture(injured=True),self.fixture(wrong_team=True)):
            with tempfile.TemporaryDirectory() as tmp:rows,_,_=collect(NOW,Path(tmp),{'version':'base'},corrected,norm,fetch)
            self.assertFalse(rows)

    def test_preseason_excluded_without_player_or_injury_requests(self):
        def fetch(url):
            self.assertIn('/scoreboard?',url)
            return {'events':[{'id':'pre','season':{'type':1}}]}
        with tempfile.TemporaryDirectory() as tmp:rows,status,_=collect(NOW,Path(tmp),{'version':'base'},corrected,norm,fetch)
        self.assertFalse(rows);self.assertEqual(status['status'],'PRESEASON_EXCLUDED')

    def test_history_excludes_wrong_season_team_phase_and_live_game(self):
        d=log(2027,['2026-10-01T00:00:00Z','2026-10-06T01:00:00Z'])
        self.assertEqual(len(history(d,2027,TEAM,NOW)),1)
        self.assertFalse(history(d,2026,TEAM,NOW))
        self.assertFalse(history(d,2027,dict(TEAM,abbreviation='BOS'),NOW))
        d['seasonTypes'][0]['displayName']='2026-27 Preseason';self.assertFalse(history(d,2027,TEAM,NOW))

    def test_playing_time_changes_projection_and_insufficient_history_blocks(self):
        cur=history(log(2027,['2026-10-03T00:00:00Z','2026-10-01T00:00:00Z','2026-09-29T00:00:00Z']),2027,TEAM,NOW)
        prior=history(log(2026,[(datetime(2026,4,1,tzinfo=timezone.utc)-timedelta(days=i)).isoformat() for i in range(30)]),2026,TEAM,NOW)
        # Event IDs identify whole games, so ensure fixture seasons are distinct.
        prior=[dict(r,gameId='old:'+r['gameId']) for r in prior]
        estimate,_=baseline(cur,prior,'Points',NOW)
        reduced,reason=baseline([dict(r,minutes=24) for r in cur],prior,'Points',NOW)
        self.assertIsNone(reason);self.assertLess(reduced['projection'],estimate['projection'])
        self.assertEqual(baseline(cur,[],'Points',NOW)[1],'insufficient_history')

    def test_three_pointer_parsing_and_missing_stats(self):
        self.assertEqual(stat_value('3-Pointers Made','2-6'),2)
        self.assertEqual(stat_value('Points','0'),0)
        self.assertIsNone(stat_value('Points','--'))

    def test_final_result_exact_team_and_dnp(self):
        for dnp,expected in ((False,'GRADED'),(True,'VOID')):
            row={'sport':'NBA','season':2027,'gameId':'1','playerId':'99','teamId':'13','opponentId':'25',
                 'prop':'Points','target':25,'resultStatus':'PENDING','startTime':'2026-10-01T00:00:00Z'}
            summary={'header':{'id':'1','season':{'year':2027,'type':2},'competitions':[{'status':{'type':{'completed':True}},'competitors':[{'team':{'id':'13'}},{'team':{'id':'25'}}]}]},
                     'boxscore':{'players':[{'team':{'id':'13'},'statistics':[{'labels':['MIN','PTS'],'athletes':[{'athlete':{'id':'99'},'stats':['30','25'],'didNotPlay':dnp}]}]}]}}
            with tempfile.TemporaryDirectory() as tmp:grade([row],NOW,Path(tmp),lambda _:summary)
            self.assertEqual(row['resultStatus'],expected)
            if not dnp:self.assertEqual(row['outcome'],1)
            row['resultStatus']='PENDING';summary['header']['season']['type']=1
            with tempfile.TemporaryDirectory() as tmp:grade([row],NOW,Path(tmp),lambda _:summary)
            self.assertEqual(row['resultStatus'],'PENDING')

if __name__=='__main__':unittest.main()
