"""Optional credentialed Sleeper board via documented ParlayAPI /props.
Default eight total board calls/day target at most 744 credits / 31 days.
Only eligible sports are polled; no pagination is performed automatically. No API key is saved.
"""
import os,json,urllib.request,urllib.parse,urllib.error,math
from datetime import datetime,timezone,timedelta
from pathlib import Path
SPORTS={'MLB':'baseball_mlb','NFL':'americanfootball_nfl','NBA':'basketball_nba','NHL':'icehockey_nhl'}
MARKETS={'player_hits':'Hits','player_total_bases':'Bases','player_hits_runs_rbis':'Hits + Runs + RBI','player_runs':'Runs','player_rbis':'RBI','player_walks':'Walks','player_stolen_bases':'Stolen Bases','player_home_runs':'Home Runs','player_pass_yds':'Pass Yards','player_pass_yards':'Pass Yards','player_pass_tds':'Pass TDs','player_pass_completions':'Pass Completions','player_rush_yds':'Rush Yards','player_rush_yards':'Rush Yards','player_rec_yds':'Receiving Yards','player_receiving_yards':'Receiving Yards','player_receptions':'Receptions','player_targets':'Targets','player_rush_attempts':'Rush Attempts','player_pass_attempts':'Pass Attempts','player_rush_reception_yds':'Rush + Receiving Yards','player_fantasy_points':'Fantasy Points PPR'}
MARKETS.update({'player_bat_walks':'Walks','player_passing_yards':'Pass Yards','player_passing_touchdowns':'Pass TDs','player_passing_attempts':'Pass Attempts','player_rushing_yards':'Rush Yards','player_rushing_attempts':'Rush Attempts','player_rushing_and_receiving_yards':'Rush + Receiving Yards'})
NFL_NAMES=dict(zip('ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS'.split(),['Arizona Cardinals','Atlanta Falcons','Baltimore Ravens','Buffalo Bills','Carolina Panthers','Chicago Bears','Cincinnati Bengals','Cleveland Browns','Dallas Cowboys','Denver Broncos','Detroit Lions','Green Bay Packers','Houston Texans','Indianapolis Colts','Jacksonville Jaguars','Kansas City Chiefs','Los Angeles Chargers','Los Angeles Rams','Las Vegas Raiders','Miami Dolphins','Minnesota Vikings','New England Patriots','New Orleans Saints','New York Giants','New York Jets','Philadelphia Eagles','Pittsburgh Steelers','Seattle Seahawks','San Francisco 49ers','Tampa Bay Buccaneers','Tennessee Titans','Washington Commanders']))

def fetch(root,now,eligible_sports=None):
    key=os.environ.get('PARLAY_API_KEY','').strip()
    path=Path(root)/'feed-state.json'
    state=json.loads(path.read_text()) if path.exists() else {'month':now.strftime('%Y-%m'),'creditsUsed':0,'sports':{}}
    if not key:return {'status':'NEEDS_API_KEY','sports':{}},state
    if state['month']!=now.strftime('%Y-%m'):state={'month':now.strftime('%Y-%m'),'creditsUsed':0,'sports':{}}
    active=[s for s in SPORTS if eligible_sports is None or s in eligible_sports]
    default_minutes=1440*max(1,len(active))//8
    interval=max(15,int(os.environ.get('PICKEM_REFRESH_MINUTES',str(default_minutes))))*60
    cap=max(0,int(os.environ.get('PARLAY_MONTHLY_CREDIT_CAP','900')))
    daily_cap=max(0,int(os.environ.get('PARLAY_DAILY_CREDIT_CAP','24')))
    day=now.strftime('%Y-%m-%d')
    if state.get('day')!=day:
        # Include known same-day board reads when migrating older state.
        known=sum(3 for entry in state['sports'].values() if datetime.fromtimestamp(entry.get('fetchedAtEpoch',0),timezone.utc).strftime('%Y-%m-%d')==day)
        state.update(day=day,dailyCreditsUsed=known)
    def read_usage(headers):
        for header,field in [('x-requests-used','providerCreditsUsed'),('x-requests-remaining','providerCreditsRemaining')]:
            try:
                value=int(headers.get(header))
                if value<0:continue
            except (ValueError,TypeError):continue
            state[field]=value
            if field=='providerCreditsUsed':state['creditsUsed']=max(state['creditsUsed'],value)
    def retry_seconds(entry):
        if entry.get('status')=='OBSERVED_BOARD':return interval
        return 0 if entry.get('status')=='UNAVAILABLE' and not entry.get('errorCode') else 900
    for sport in active:
        old=state['sports'].get(sport,{})
        if now.timestamp()-old.get('fetchedAtEpoch',0)<retry_seconds(old):continue
        if state['creditsUsed']+3>cap or state['dailyCreditsUsed']+3>daily_cap:break
        if state.get('providerCreditsRemaining',3)<3:break
        url='https://parlay-api.com/v1/sports/'+SPORTS[sport]+'/props?'+urllib.parse.urlencode({'bookmakers':'sleeper','maxAgeSec':900,'limit':5000,'grouped':'false'})
        req=urllib.request.Request(url,headers={'X-API-Key':key,'User-Agent':'MultiSport-Pickem/0.5.2'})
        state['creditsUsed']+=3;state['dailyCreditsUsed']+=3
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                read_usage(response.headers)
                rows=json.load(response);headers=response.headers
            if not isinstance(rows,list):raise ValueError('Expected prop list')
            kept=[r for r in rows if r.get('bookmaker')=='sleeper']
            state['sports'][sport]={'status':'OBSERVED_BOARD','rows':kept,'fetchedAtEpoch':now.timestamp(),'hasMore':headers.get('x-result-has-more')=='true','truncated':headers.get('x-result-truncated')=='true','degraded':headers.get('x-result-degraded') or None}
        except urllib.error.HTTPError as error:
            read_usage(error.headers or {})
            state['sports'][sport]={'status':'UNAVAILABLE','rows':[],'fetchedAtEpoch':now.timestamp(),'httpStatus':error.code,'errorCode':'HTTP_'+str(error.code)}
        except Exception as error:
            code='INVALID_RESPONSE' if isinstance(error,(ValueError,TypeError)) else 'NETWORK_ERROR'
            state['sports'][sport]={'status':'UNAVAILABLE','rows':[],'fetchedAtEpoch':now.timestamp(),'errorCode':code}
    next_at=None;reason=None
    if active:
        if state['creditsUsed']+3>cap or state.get('providerCreditsRemaining',3)<3:
            first=now.replace(day=1,hour=0,minute=0,second=0,microsecond=0)
            next_at=(first+timedelta(days=32)).replace(day=1);reason='MONTHLY_BUDGET'
        elif state['dailyCreditsUsed']+3>daily_cap:
            next_at=now.replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1);reason='DAILY_BUDGET'
        else:
            due=min(state['sports'].get(s,{}).get('fetchedAtEpoch',0)+retry_seconds(state['sports'].get(s,{})) for s in active)
            next_at=datetime.fromtimestamp(max(now.timestamp(),due),timezone.utc);reason='SCHEDULED'
    return {'status':'CONFIGURED','sports':state['sports'],'creditsUsed':state['creditsUsed'],'creditCap':cap,
            'dailyCreditsUsed':state['dailyCreditsUsed'],'dailyCreditCap':daily_cap,'eligibleSports':active,
            'refreshMinutes':interval//60,'nextRefreshAt':next_at.isoformat() if next_at else None,'refreshReason':reason},state

def match(forecasts,board,now,norm):
    out=[];counts={'observed':0,'matched':0,'missingOfferType':0,'missingKickoff':0}
    def teams(r):
        if r['sport']=='NFL':
            return NFL_NAMES.get(r.get('homeTeamAbbr')),NFL_NAMES.get(r.get('awayTeamAbbr'))
        return r.get('homeTeam'),r.get('awayTeam')
    # Resolve a provider's dated fixture only from explicit official-schedule metadata.
    fixtures={}
    for r in forecasts:
        home,away=teams(r)
        if not r.get('scheduleVerified') or not r.get('officialGameDate') or not home or not away:continue
        key=(r['sport'],r['officialGameDate'],norm(home),norm(away))
        fixtures.setdefault(key,set()).add((str(r['gameId']),r['startTime']))
    for sport,entry in board.get('sports',{}).items():
        elapsed=now.timestamp()-entry.get('fetchedAtEpoch',0)
        if elapsed<0 or elapsed>900:continue
        for line in entry.get('rows',[]):
            counts['observed']+=1
            if line.get('bookmaker')!='sleeper' or line.get('sport_key',SPORTS[sport])!=SPORTS[sport]:continue
            types=[str(line[key]).lower() for key in ('odds_type','projection_type') if key in line]
            unknown_type=not types
            if unknown_type:counts['missingOfferType']+=1
            reported=line.get('commence_time_reported') is True
            if not reported:counts['missingKickoff']+=1
            # Missing classification is a review flag, never an invented "standard" label.
            # Explicit special variants and inconsistent/null tags remain excluded.
            if line.get('period')!='FULL' or (types and any(t!='standard' for t in types)):continue
            if unknown_type and line.get('is_dfs_flat_payout') is not True:continue
            if not line.get('canonical_event_id'):continue
            try:
                value=float(line['line']);age=float(line['age_seconds'])+elapsed
                if not math.isfinite(value) or not math.isfinite(age) or not 0<=age<=900:continue
                if reported:
                    start=datetime.fromisoformat(line['commence_time'].replace('Z','+00:00'))
                    if start.tzinfo is None:continue
                    fixture_id=None;start_source='PROVIDER'
                else:
                    # Contradictory timestamps are not repaired. Teamless/date-less fixtures are rejected.
                    if line.get('commence_time') is not None:continue
                    key=(sport,line.get('game_date'),norm(line.get('home_team')),norm(line.get('away_team')))
                    events=fixtures.get(key,set())
                    if len(events)!=1:continue
                    fixture_id,official_start=next(iter(events))
                    start=datetime.fromisoformat(official_start.replace('Z','+00:00'))
                    if start.tzinfo is None:continue
                    start_source='OFFICIAL_SCHEDULE'
                if start<=now:continue
            except (ValueError,TypeError,KeyError,AttributeError):continue
            prop=MARKETS.get(line.get('market_key'))
            candidates=[]
            for r in forecasts:
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
            if len(candidates)!=1:continue
            r=dict(candidates[0],platform='Sleeper',platformLine=value,platformEventId=line['canonical_event_id'],actionable=True,
                   offerObservedAt=datetime.fromtimestamp(now.timestamp()-age,timezone.utc).isoformat(),
                   provider='ParlayAPI',payoutMultiplier=None,platformOfferType='unreported' if unknown_type else 'standard',
                   requiresPlatformReview=unknown_type,kickoffSource=start_source)
            r['offerId']=f"Sleeper:{sport}:{r['platformEventId']}:{r['playerId']}:{r['prop']}:FULL:MORE:{value}"
            if not any(x['offerId']==r['offerId'] for x in out):out.append(r);counts['matched']+=1
    return out,counts

def slips(picks,size,count=5):
    """Bounded beam search; independent-event estimate, no global-optimum claim."""
    if size not in (2,3,4,5,6,8):raise ValueError('Unsupported slip size')
    pool=sorted(picks,key=lambda r:-r['probability'])[:200]
    beam=[(1.0,[],set(),set())]
    for i,r in enumerate(pool):
        if not r.get('actionable') or r.get('platform')!='Sleeper':continue
        player=r['sport']+':'+str(r['playerId']);event=r['sport']+':'+str(r['gameId'])
        added=[]
        for p,legs,players,events in beam:
            if len(legs)<size and player not in players and event not in events:
                added.append((p*r['probability'],legs+[r],players|{player},events|{event}))
        buckets={}
        for item in beam+added:buckets.setdefault(len(item[1]),[]).append(item)
        beam=[]
        for length,items in buckets.items():beam.extend(sorted(items,key=lambda v:-v[0])[:128])
    final=sorted((x for x in beam if len(x[1])==size),key=lambda v:-v[0])[:count]
    return [{'legs':legs,'probability':p,'method':'INDEPENDENT_EVENTS_ESTIMATE','payoutMultiplier':None} for p,legs,_,_ in final]
