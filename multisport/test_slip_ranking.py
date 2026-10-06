import itertools,math,random,unittest
from platform_feed import slip_sets,slips

def offer(event,player,probability,variant=0):
    return {'offerId':f'{event}:{player}:{variant}','sport':'MLB','gameId':event,'playerId':player,
            'prop':'Hits','platformLine':variant+0.5,'probability':probability,
            'actionable':True,'platform':'Sleeper'}

class SlipRankingTests(unittest.TestCase):
    def exhaustive(self,pool,size,count=5):
        candidates=[]
        for rows in itertools.combinations(pool,size):
            if len({r['gameId'] for r in rows})!=size or len({r['playerId'] for r in rows})!=size:continue
            rows=sorted(rows,key=lambda r:str(r['gameId']))
            candidates.append((math.prod(r['probability'] for r in rows),tuple(sorted(r['offerId'] for r in rows))))
        return sorted(candidates,key=lambda item:(-item[0],item[1]))[:count]
    def test_exact_ranking_matches_exhaustive_search_across_random_pools(self):
        rng=random.Random(810)
        for case in range(20):
            pool=[offer(event,event*10+player,rng.uniform(.25,.95)) for event in range(5) for player in range(2)]
            result=slip_sets(pool,(2,3,4))
            for size in (2,3,4):
                expected=self.exhaustive(pool,size)
                actual=result[str(size)]
                self.assertEqual([tuple(sorted(r['offerId'] for r in s['legs'])) for s in actual],[key for p,key in expected])
                for s,(p,key) in zip(actual,expected):
                    self.assertAlmostEqual(s['probability'],p);self.assertTrue(s['searchComplete'])
    def test_offers_beyond_old_200_cutoff_preserve_games_needed_for_eight_legs(self):
        pool=[offer('dominant',i,.95,variant=i) for i in range(210)]
        pool += [offer(f'other-{i}',300+i,.6) for i in range(7)]
        result=slips(pool,8)
        self.assertTrue(result);self.assertTrue(result[0]['searchComplete'])
        self.assertEqual(len({r['gameId'] for r in result[0]['legs']}),8)
    def test_input_order_and_ties_are_deterministic_and_duplicates_are_removed(self):
        pool=[offer(event,event*10+player,.7) for event in range(4) for player in range(3)]
        original=slip_sets(pool,(2,4));random.Random(12).shuffle(pool)
        self.assertEqual(slip_sets(pool+pool,(2,4)),original)
        for rows in original.values():
            signatures=[tuple(sorted(r['offerId'] for r in s['legs'])) for s in rows]
            self.assertEqual(len(set(signatures)),len(signatures))
    def test_cross_game_player_conflicts_use_labelled_bounded_fallback(self):
        pool=[offer(1,1,.9),offer(2,1,.8),offer(2,2,.7),offer(3,3,.6)]
        result=slip_sets(pool,(2,3))
        for rows in result.values():
            for slip in rows:
                self.assertFalse(slip['searchComplete'])
                self.assertEqual(slip['rankingMethod'],'BOUNDED_PLAYER_BEAM')
                self.assertEqual(len({r['playerId'] for r in slip['legs']}),len(slip['legs']))
                self.assertEqual(len({r['gameId'] for r in slip['legs']}),len(slip['legs']))
        self.assertAlmostEqual(result['3'][0]['probability'],.9*.7*.6)
    def test_invalid_probabilities_and_ineligible_rows_cannot_enter_slips(self):
        valid=[offer(1,1,.8),offer(2,2,.7)]
        invalid=[offer(3,3,p) for p in (float('nan'),float('inf'),-.1,1.1,True,0)]
        invalid += [dict(offer(4,4,.99),platformEligible=False),dict(offer(5,5,.99),actionable=False),dict(offer(6,6,.99),platform='Other')]
        result=slips(valid+invalid,2)
        self.assertEqual(len(result),1);self.assertAlmostEqual(result[0]['probability'],.56)
    def test_all_sizes_are_built_together_and_requested_limit_is_respected(self):
        pool=[offer(event,event*10+i,.8-i*.01) for event in range(8) for i in range(3)]
        result=slip_sets(pool,count=3)
        for size,rows in result.items():
            self.assertEqual(len(rows),3)
            self.assertTrue(all(len(s['legs'])==int(size) for s in rows))
        self.assertEqual(slip_sets(pool,(2,),count=0),{'2':[]})
        with self.assertRaises(ValueError):slips(pool,7)

if __name__=='__main__':unittest.main()
