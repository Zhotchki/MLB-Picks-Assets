"""Optional credentialed Sleeper board via documented ParlayAPI /props.
Default eight total board calls/day target at most 744 credits / 31 days.
Only eligible sports are polled; no pagination is performed automatically. No API key is saved.
"""
import os,json,urllib.request,urllib.parse,urllib.error,math
from datetime import datetime,timezone,timedelta
from pathlib import Path
SPORTS={'MLB':'baseball_mlb','NFL':'americanfootball_nfl','NBA':'basketball_nba','NHL':'icehockey_nhl'}
MARKETS={'player_hits':'Hits','player_total_bases':'Bases','player_hits_runs_rbis':'Hits + Runs + RBI','player_runs':'Runs','player_rbis':'RBI','player_walks':'Walks','player_stolen_bases':'Stolen Bases','player_home_runs':'Home Runs','player_pass_yds':'Pass Yards','player_pass_yards':'Pass Yards','player_pass_tds':'Pass TDs','player_pass_completions':'Pass Completions','player_rush_yds':'Rush Yards','player_rush_yards':'Rush …1854 tokens truncated…    if state['creditsUsed']+3>cap or state.get('providerCreditsRemaining',3)<3:
            first=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
            next_at=(first+timedelta(days=32)).replace(day=1);reason='MONTHLY_BUDGET'
        elif state['dailyCreditsUsed']+3>daily_cap:
            next_at=now.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1);reason='DAILY_BUDGET'
        elif planned:
            remaining=[slot for slot in checks if slot['sport'] in active and pending(slot)]
            next_at=max(now,remaining[0]['at']) if remaining else None;reason='PREGAME_WINDOW' if remaining else 'WAITING_FOR_GAMES'
        else:
            due=min(state['sports'].get(s,{}).get('fetchedAtEpoch',0)+retry_seconds(state['sports'].get(s,{})) for s in active)
            next_at=datetime.fromtimestamp(max(now.timestamp(),due),timezone.utc);reason='SCHEDULED'
    return {'status':'CONFIGURED','sports':state['sports'],'creditsUsed':state['creditsUsed'],'creditCap':cap,
            'dailyCreditsUsed':state['dailyCreditsUsed'],'dailyCreditCap':daily_cap,'eligibleSports':active,
            'refreshMinutes':None if planned else interval//60,'refreshMode':'PREGAME_WINDOWS' if planned else 'INTERVAL','plannedChecks':[{'sport':slot['sport'],'checkAt':slot['at'].isoformat(),'leadMinutes':slot['leadMinutes'],'games':len(slot['games'])} for slot in checks if slot['until']>=now],'nextRefreshAt':next_at.isoformat() if next_at else None,'refreshReason':reason},state

def match(forecasts,board,now,norm):
    out=[];counts={'observed':0,'matched':0,'missingOfferType':0,'missingKickoff':0,'excluded':{}}
    def reject(reason,n=1):counts['excluded'][reason]=counts['excluded'].get(reason,0)+n
    def teams(r):
        if r['sport']=='NFL':
            return NFL_NAMES.get(r.get('homeTeamAbbr')),NFL_NAMES.get(r.get('awayTeamAbbr'))
        return r.get('homeTeam'),r.get('awayTeam')
    # Resolve a provider's dated fixture only from explicit official-schedule metadata.
    fixtures={};forecast_index={}
    for r in forecasts:
        if r.get('platformEligible') is not False:
            forecast_index.setdefault((r.get('sport'),r.get('prop'),norm(r.get('player'))),[]).append(r)
        home,away=teams(r)
        if not r.get('scheduleVerified') or not r.get('officialGameDate') or not home or not away:continue
        key=(r['sport'],r['officialGameDate'],norm(home),norm(away))
        fixtures.setdefault(key,set()).add((str(r['gameId']),r['startTime']))
    for sport,entry in board.get('sports',{}).items():
        rows=entry.get('rows',[]);counts['observed']+=len(rows)
        if board.get('eligibleSports') is not None and sport not in board['eligibleSports']:
            reject('sport_not_eligible',len(rows));continue
        elapsed=now.timestamp()-entry.get('fetchedAtEpoch',0)
        if elapsed<0:reject('invalid_board_time',len(rows));continue
        if elapsed>900:reject('expired_board',len(rows));continue
        for line in rows:
            if line.get('bookmaker')!='sleeper' or line.get('sport_key',SPORTS[sport])!=SPORTS[sport]:
                reject('unsupported_source');continue
            types=[str(line[key]).lower() for key in ('odds_type','projection_type') if key in line]
            unknown_type=not types
            if unknown_type:counts['missingOfferType']+=1
            reported=line.get('commence_time_reported') is True
            if not reported:counts['missingKickoff']+=1
            # Missing classification is a review flag, never an invented "standard" label.
            # Explicit special variants and inconsistent/null tags remain excluded.
            if line.get('period')!='FULL':reject('unsupported_period');continue
            if types and any(t!='standard' for t in types):reject('special_offer_type');continue
            if unknown_type and line.get('is_dfs_flat_payout') is not True:reject('unverified_offer_type');continue
            if not line.get('canonical_event_id'):reject('missing_event_identity');continue
            try:
                value=float(line['line']);age=float(line['age_seconds'])+elapsed
                if not math.isfinite(value) or not math.isfinite(age) or age<0:reject('invalid_line_or_age');continue
                if age>900:reject('expired_line');continue
                if reported:
                    start=datetime.fromisoformat(line['commence_time'].replace('Z','+00:00'))
                    if start.tzinfo is None:reject('unverified_kickoff');continue
                    fixture_id=None;start_source='PROVIDER'
                else:
                    # Contradictory timestamps are not repaired. Teamless/date-less fixtures are rejected.
                    if line.get('commence_time') is not None:reject('contradictory_kickoff');continue
                    key=(sport,line.get('game_date'),norm(line.get('home_team')),norm(line.get('away_team')))
                    events=fixtures.get(key,set())
                    if len(events)!=1:reject('unresolved_fixture');continue
                    fixture_id,official_start=next(iter(events))
                    start=datetime.fromisoformat(official_start.replace('Z','+00:00'))
                    if start.tzinfo is None:continue
                    start_source='OFFICIAL_SCHEDULE'
                if start<=now:reject('game_started');continue
            except (ValueError,TypeError,KeyError,AttributeError):reject('invalid_line_or_kickoff');continue
            prop=MARKETS.get(line.get('market_key'))
            if not prop:reject('unsupported_market');continue
            candidates=[]
            for r in forecast_index.get((sport,prop,norm(line.get('player'))),[]):
                if r.get('platformEligible') is False:continue
                if r['sport']!=sport or r['prop']!=prop or norm(r['player'])!=norm(line.get('player')):continue
                if abs((datetime.fromisoformat(r['startTime'].replace('Z','+00:00'))-start).total_seconds())>300:continue
                home,away=teams(r)
                # Legacy NFL fixtures with reported kickoffs can still verify the team pair.
                if sport=='NFL' and not home and not away and reported:
                    pair=[NFL_NAMES.get(r['team']),NFL_NAMES.get(r['opponent'])]
                    if None in pair or {norm(t) for t in pair}!={norm(line.get('home_team')),norm(line.get('away_team'))}:continue
                elif not home or not away or (norm(home),norm(away))!=(norm(line.get('home_team')),norm(line.get('away_team'))):continue
                if fixture_id is not None and str(r['gameId'])!=fixture_id:continue
                model_line=r.get('modelLine',r['target']-.5)
                if r['direction']!='MORE' or abs(model_line-value)>1e-9:continue
                candidates.append(r)
            if len(candidates)!=1:
                indexed=forecast_index.get((sport,prop,norm(line.get('player'))),[])
                reason='ambiguous_match' if len(candidates)>1 else 'no_player_prop_forecast' if not indexed else 'unmatched_model_line' if not any(abs(r.get('modelLine',r['target']-.5)-value)<=1e-9 for r in indexed) else 'fixture_mismatch'
                reject(reason);continue
            r=dict(candidates[0],platform='Sleeper',platformLine=value,platformEventId=line['canonical_event_id'],actionable=True,
                   offerObservedAt=datetime.fromtimestamp(now.timestamp()-age,timezone.utc).isoformat(),
                   provider='ParlayAPI',payoutMultiplier=None,platformOfferType='unreported' if unknown_type else 'standard',
                   requiresPlatformReview=unknown_type,kickoffSource=start_source)
            r['offerId']=f"Sleeper:{sport}:{r['platformEventId']}:{r['playerId']}:{r['prop']}:FULL:MORE:{value}"
            if not any(x['offerId']==r['offerId'] for x in out):out.append(r);counts['matched']+=1
            else:reject('duplicate_offer')
    return out,counts

def _offer_key(row):
    return str(row.get('offerId') or row.get('id') or '|'.join(str(row.get(k,'')) for k in ('sport','gameId','playerId','prop','direction','platformLine')))

def _player(row):return str(row['sport'])+':'+str(row['playerId'])
def _event(row):return str(row['sport'])+':'+str(row['gameId'])

def slip_sets(picks,sizes=(2,3,4,5,6,8),count=5):
    """Rank all requested sizes once; exact event DP unless players repeat across events."""
    sizes=sorted(set(sizes))
    if any(size not in (2,3,4,5,6,8) for size in sizes):raise ValueError('Unsupported slip size')
    if not sizes:return {}
    if count<1:return {str(size):[] for size in sizes}
    pool=[]
    for row in picks:
        try:p=float(row['probability'])
        except (KeyError,ValueError,TypeError):continue
        if isinstance(row['probability'],bool) or not math.isfinite(p) or not 0<p<=1:continue
        if row.get('actionable') is not True or row.get('platform')!='Sleeper' or row.get('platformEligible') is False:continue
        if any(row.get(key) is None for key in ('sport','gameId','playerId')):continue
        pool.append(dict(row,probability=p))
    return rank_pool(pool,sizes,count)

def rank_pool(pool,sizes,count):
    """Pure ranking shared by live offers and separately labeled model tests."""
    sizes=sorted(set(sizes))
    if not sizes:return {}
    if count<1:return {str(size):[] for size in sizes}
    pool=list(pool)
    pool.sort(key=lambda row:(-row['probability'],_offer_key(row)))
    seen=set();unique=[]
    for row in pool:
        key=_offer_key(row)
        if key in seen:continue
        seen.add(key);unique.append(row)
    groups={};player_events={}
    for row in unique:
        groups.setdefault(_event(row),[]).append(row)
        player_events.setdefault(_player(row),set()).add(_event(row))
    maximum=min(max(sizes),len(groups))
    def rank(item):return -item[0],tuple(sorted(_offer_key(row) for row in item[1]))
    complete=all(len(events)==1 for events in player_events.values())
    dp={0:[(1.0,[])]}
    if complete:
        # All choices from an event have the same future feasibility. The best K
        # prefixes per leg count and best K offers per event suffice for the exact top K.
        for event in sorted(groups):
            options=groups[event][:count]
            for length in range(maximum,0,-1):
                candidates=dp.get(length,[])+[(p*row['probability'],legs+[row]) for p,legs in dp.get(length-1,[]) for row in options]
                dp[length]=sorted(candidates,key=rank)[:count]
        method='EXACT_EVENT_DP'
    else:
        # Cross-event player conflicts invalidate event-only dominance. Preserve
        # a bounded player-aware fallback and explicitly label its ranking limit.
        beam=[(1.0,[],set(),set())]
        for row in unique:
            player,event=_player(row),_event(row)
            added=[(p*row['probability'],legs+[row],players|{player},events|{event})
                   for p,legs,players,events in beam if len(legs)<maximum and player not in players and event not in events]
            buckets={}
            for item in beam+added:buckets.setdefault(len(item[1]),[]).append(item)
            beam=[item for items in buckets.values() for item in sorted(items,key=rank)[:max(128,count)]]
        dp={length:sorted([(item[0],item[1]) for item in beam if len(item[1])==length],key=rank)[:count] for length in sizes}
        method='BOUNDED_PLAYER_BEAM'
    return {str(size):[{'legs':legs,'probability':p,'method':'INDEPENDENT_EVENTS_ESTIMATE',
                       'rankingMethod':method,'searchComplete':complete,'payoutMultiplier':None}
                      for p,legs in dp.get(size,[])] for size in sizes}

def slips(picks,size,count=5):
    return slip_sets(picks,(size,),count)[str(size)]
