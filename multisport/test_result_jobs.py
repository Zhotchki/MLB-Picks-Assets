import unittest,tempfile
from datetime import datetime,timezone
from pathlib import Path
from threading import Barrier,Lock
from unittest.mock import patch
from result_jobs import load_results

NOW=datetime(2030,1,2,tzinfo=timezone.utc)

class ResultJobsTests(unittest.TestCase):
    def test_empty_pool_has_no_reads(self):
        rows,health=load_results([],lambda _:self.fail('Unexpected request'))
        self.assertFalse(rows);self.assertEqual(health['gradingGamesChecked'],0)

    def test_failed_game_and_duplicate_targets_do_not_block_others(self):
        calls=[]
        def fetch(gid):
            calls.append(gid)
            if gid==1:raise TimeoutError('Unavailable')
            return {'id':gid}
        rows,health=load_results([1,1,2,2],fetch)
        self.assertEqual(sorted(calls),[1,2]);self.assertEqual(rows,{2:{'id':2}})
        self.assertEqual(health['gradingGamesUnavailable'],1)
        self.assertEqual(health['gradingStatus'],'PARTIAL_RESULT_SOURCE')

    def test_separate_games_are_read_concurrently_with_four_worker_limit(self):
        barrier=Barrier(4);lock=Lock();active=peak=0
        def fetch(gid):
            nonlocal active,peak
            with lock:active+=1;peak=max(peak,active)
            barrier.wait(timeout=5)
            with lock:active-=1
            return gid
        rows,health=load_results(range(8),fetch)
        self.assertEqual(len(rows),8);self.assertEqual(peak,4)
        self.assertEqual(health['gradingGamesUnavailable'],0)

    def test_mlb_failed_game_stays_pending_and_retry_preserves_forecast(self):
        from update import grade_mlb
        rows=[{'sport':'MLB','gameId':gid,'playerId':99,'prop':'Hits','target':1,
               'startTime':'2030-01-01T16:00:00Z','capturedAt':'2030-01-01T14:00:00Z',
               'probability':.7,'resultStatus':'PENDING'} for gid in (1,2)]
        failed={1};calls=[]
        def fetch(url):
            if 'schedule?' in url:
                gid=int(url.split('gamePk=')[1]);calls.append(gid)
                if gid in failed:raise TimeoutError()
                return {'dates':[{'games':[{'gamePk':gid,'status':{'abstractGameState':'Final','codedGameState':'F'}}]}]}
            return {'teams':{'home':{'players':{'99':{'person':{'id':99},'stats':{'batting':{'plateAppearances':4,'hits':0}}}}}}}
        with patch('update.get',fetch):
            health=grade_mlb(rows,NOW)
            self.assertEqual([r['resultStatus'] for r in rows],['PENDING','GRADED'])
            self.assertEqual(rows[1]['outcome'],0);self.assertNotIn('outcome',rows[0])
            failed.clear();grade_mlb(rows,NOW)
        self.assertEqual(calls.count(2),1);self.assertEqual(rows[0]['resultStatus'],'GRADED')
        self.assertTrue(all(r['probability']==.7 and r['capturedAt']=='2030-01-01T14:00:00Z' for r in rows))
        self.assertEqual(health['gradingGamesUnavailable'],1)

    def test_nhl_failed_game_does_not_block_verified_final(self):
        from nhl_adapter import grade
        rows=[{'sport':'NHL','season':20292030,'gameId':gid,'playerId':99,'team':'TOR','opponent':'NSH',
               'target':1,'startTime':'2030-01-01T16:00:00Z','resultStatus':'PENDING'} for gid in (1,2)]
        def fetch(url):
            gid=int(url.split('/gamecenter/')[1].split('/')[0])
            if gid==1:raise TimeoutError()
            return {'id':gid,'season':20292030,'gameType':2,'gameState':'OFF','homeTeam':{'abbrev':'TOR'},'awayTeam':{'abbrev':'NSH'},
                    'playerByGameStats':{'homeTeam':{'forwards':[{'playerId':99,'toi':'20:00','sog':0}]}}}
        with tempfile.TemporaryDirectory() as root:health=grade(rows,NOW,Path(root),fetch)
        self.assertEqual([r['resultStatus'] for r in rows],['PENDING','GRADED'])
        self.assertEqual(rows[1]['outcome'],0);self.assertEqual(health['gradingGamesUnavailable'],1)

    def test_nba_failed_game_does_not_block_verified_final(self):
        from nba_adapter import grade
        rows=[{'sport':'NBA','season':2030,'gameId':gid,'playerId':'99','teamId':'13','opponentId':'25','prop':'Points',
               'target':1,'startTime':'2030-01-01T16:00:00Z','resultStatus':'PENDING'} for gid in ('1','2')]
        def fetch(url):
            gid=url.split('event=')[1]
            if gid=='1':raise TimeoutError()
            return {'header':{'id':gid,'season':{'year':2030,'type':2},'competitions':[{'status':{'type':{'completed':True}},'competitors':[{'team':{'id':'13'}},{'team':{'id':'25'}}]}]},
                    'boxscore':{'players':[{'team':{'id':'13'},'statistics':[{'labels':['MIN','PTS'],'athletes':[{'athlete':{'id':'99'},'stats':['30','0']}]}]}]}}
        with tempfile.TemporaryDirectory() as root:health=grade(rows,NOW,Path(root),fetch)
        self.assertEqual([r['resultStatus'] for r in rows],['PENDING','GRADED'])
        self.assertEqual(rows[1]['outcome'],0);self.assertEqual(health['gradingGamesUnavailable'],1)
