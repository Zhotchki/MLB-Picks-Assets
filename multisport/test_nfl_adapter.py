import unittest
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch
from collections import Counter
import nfl_adapter
from update import norm,corrected
class NFLTests(unittest.TestCase):
    def fixtures(self):
        now=datetime(2030,1,3,14,tzinfo=timezone.utc)
        game={'game_id':'2030_01_AA_BB','season':'2030','week':'1','game_type':'REG','gameday':'2030-01-03','gametime':'16:00','home_team':'BB','away_team':'AA','home_score':'','away_score':''}
        row={'Player':'Fixture Player','Team':'AA','Opponent':'BB','Market':'Receptions','Line':3.5,'Model Side':'Higher','Probability':.65,'History Sample':8,'Expected Snap %':.8,'Availability':'Active','Line Source':'Automatic model target','Model Projection':5}
        feed={'generatedAt':now.isoformat(),'lastRefresh':'1/3/2030 07:59:00','season':2030,'week':1,'appVersion':'fixture','picks':[row],'projections':[{'Player':'Fixture Player','Team':'AA','Week':1,'Player ID':'00-test'}]}
        roster={'99':{'full_name':'Fixture Player','gsis_id':'00-test','team':'AA','active':True}}
        return now,game,row,feed,roster
    def collect(self,now,game,feed,roster):
        def cache(root,name,*args):return roster if name.endswith('json') else [game]
        import tempfile
        with tempfile.TemporaryDirectory() as tmp,patch('nfl_adapter.cache_read',side_effect=cache):
            return nfl_adapter.collect(now,lambda u:feed,{'version':'baseline','offsets':{}},corrected,Path(tmp),norm)
    def test_kickoff_uses_eastern_timezone(self):
        self.assertEqual(nfl_adapter.kickoff({'gameday':'2030-01-03','gametime':'16:00'}).hour,21)
    def test_capture_retains_ids_snaps_and_forecast_line(self):
        now,g,r,feed,roster=self.fixtures();rows,status,rejected=self.collect(now,g,feed,roster)
        self.assertEqual(len(rows),1);self.assertEqual(rows[0]['playerId'],'00-test');self.assertEqual(rows[0]['expectedPlayingTime'],.8)
        self.assertEqual(rows[0]['target'],4);self.assertIsNone(rows[0]['platformLine']);self.assertFalse(rows[0]['actionable'])
    def test_roster_team_mismatch_excluded(self):
        now,g,r,feed,roster=self.fixtures();roster['99']['team']='CC'
        rows,status,rejected=self.collect(now,g,feed,roster);self.assertEqual(rows,[]);self.assertEqual(rejected['player_team_mismatch'],1)
    def test_started_game_excluded_even_if_feed_says_upcoming(self):
        now,g,r,feed,roster=self.fixtures();g['gametime']='08:00'
        rows,status,rejected=self.collect(now,g,feed,roster);self.assertEqual(rows,[]);self.assertEqual(rejected['game_started'],1)
    def test_old_underlying_refresh_excluded(self):
        now,g,r,feed,roster=self.fixtures();feed['lastRefresh']='1/1/2030 07:59:00'
        rows,status,rejected=self.collect(now,g,feed,roster);self.assertEqual(rows,[]);self.assertEqual(status['sourceStatus'],'STALE')
    def test_mismatched_projection_week_excluded(self):
        now,g,r,feed,roster=self.fixtures();feed['projections'][0]['Week']=2
        rows,status,rejected=self.collect(now,g,feed,roster);self.assertEqual(rows,[]);self.assertEqual(rejected['projection_week_or_identity'],1)
    def test_stat_loss_is_not_inferred_from_missing_data(self):
        now,g,r,feed,roster=self.fixtures();rows,_,_=self.collect(now,g,feed,roster)
        now=datetime(2030,1,4,14,tzinfo=timezone.utc);g.update(home_score='20',away_score='10')
        def cache(root,name,*args):return [g] if name=='nfl-schedule.csv' else []
        import tempfile
        with tempfile.TemporaryDirectory() as tmp,patch('nfl_adapter.cache_read',side_effect=cache):nfl_adapter.grade(rows,now,Path('.'))
        self.assertEqual(rows[0]['resultStatus'],'PENDING')
    def test_final_result_grades_strict_model_line(self):
        now,g,r,feed,roster=self.fixtures();rows,_,_=self.collect(now,g,feed,roster)
        now=datetime(2030,1,4,14,tzinfo=timezone.utc);g.update(home_score='20',away_score='10')
        stats={'player_id':'00-test','week':'1','season_type':'REG','team':'AA','opponent_team':'BB','receptions':'4'}
        with patch('nfl_adapter.cache_read',side_effect=lambda root,name,*args:[g] if name=='nfl-schedule.csv' else [stats]):nfl_adapter.grade(rows,now,Path('.'))
        self.assertEqual(rows[0]['resultStatus'],'GRADED');self.assertEqual(rows[0]['outcome'],1)
if __name__=='__main__':unittest.main()
