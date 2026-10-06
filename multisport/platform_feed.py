"""Optional credentialed Sleeper board via documented ParlayAPI /props.
Default two daily polls across four sports cost at most 744 credits / 31 days
before truncation; no pagination is performed automatically. No API key is saved.
"""
import os,json,urllib.request,urllib.parse,math
from datetime import datetime,timezone
from pathlib import Path
SPORTS={'MLB':'baseball_mlb','NFL':'americanfootball_nfl','NBA':'basketball_nba','NHL':'icehockey_nhl'}
MARKETS={'player_hits':'Hits','player_total_bases':'Bases','player_hits_runs_rbis':'Hits + Runs + RBI','player_runs':'Runs','player_rbis':'RBI','player_walks':'Walks','player_stolen_bases':'Stolen Bases','player_home_runs':'Home Runs','player_pass_yds':'Pass Yards','player_pass_yards':'Pass Yards','player_pass_tds':'Pass TDs','player_pass_completions':'Pass Completions','player_rush_yds':'Rush Yards','player_rush_yards':'Rush Yards','player_rec_yds':'Receiving Yards','player_receiving_yards':'Receiving Yards','player_receptions':'Receptions','player_targets':'Targets','player_rush_attempts':'Rush Attempts','player_pass_attempts':'Pass Attempts','player_rush_reception_yds':'Rush + Receiving Yards','player_fantasy_points':'Fantasy Points PPR'}
NFL_NAMES=dict(zip('ARI ATL BAL BUF CAR CHI CIN CLE DAL DEN DET GB HOU IND JAX KC LAC LAR LV MIA MIN NE NO NYG NYJ PHI PIT SEA SF TB TEN WAS'.split(),['Arizona Cardinals','Atlanta Falcons','Baltimore Ravens','Buffalo Bills','Carolina Panthers','Chicago Bears','Cincinnati Bengals','Cleveland Browns','Dallas Cowboys','Denver Broncos','Detroit Lions','Green Bay Packers','Houston Texans','Indianapolis Colts','Jacksonville Jaguars','Kansas City Chiefs','Los Angeles Chargers','Los Angeles Rams','Las Vegas Raiders','Miami Dolphins','Minnesota Vikings','New England Patriots','New Orleans Saints','New York Giants','New York Jets','Philadelphia Eagles','Pittsburgh Steelers','Seattle Seahawks','San Francisco 49ers','Tampa Bay Buccaneers','Tennessee Titans','Washington Commanders']))

def fetch(root,now):
    key=os.environ.get('PARLAY_API_KEY','')
    path=Path(root)/'feed-state.json'
    state=json.loads(path.read_text()) if path.exists() else {'month':now.strftime('%Y-%m'),'creditsUsed':0,'sports':{}}
    if not key:return {'status':'NEEDS_API_KEY','sports':{}},state
    if state['month']!=now.strftime('%Y-%m'):state={'month':now.strftime('%Y-%m'),'creditsUsed':0,'sports':{}}
    interval=max(15,int(os.environ.get('PICKEM_REFRESH_MINUTES','720')))*60
    cap=max(0,int(os.environ.get('PARLAY_MONTHLY_CREDIT_CAP','900')))
    for sport,api_sport in SPORTS.items():
        old=state['sports'].get(sport,{})
        if now.timestamp()-old.get('fetchedAtEpoch',0)<interval:continue
        if state['creditsUsed']+3>cap:break
        url='https://parlay-api.com/v1/sports/'+api_sport+'/props?'+urllib.parse.urlencode({'bookmakers':'sleeper','maxAgeSec':900,'limit':5000,'grouped':'false'})
        req=urllib.request.Request(url,headers={'X-API-Key':key,'User-Agent':'MultiSport-Pickem/0.3'})
        # Reserve the documented cost before request; failures cannot reset the budget.
        state['creditsUsed']+=3
        try:
            with urllib.request.urlopen(req,timeout=30) as response:
                rows=json.load(response);headers=response.headers
            if not isinstance(rows,list):raise ValueError('Expected prop list')
            kept=[r for r in rows if r.get('bookmaker')=='sleeper']
            state['sports'][sport]={'status':'OBSERVED_BOARD','rows':kept,'fetchedAtEpoch':now.timestamp(),'hasMore':headers.get('x-result-has-more')=='true','truncated':headers.get('x-result-truncated')=='true','degraded':headers.get('x-result-degraded') or None}
        except Exception:
            state['sports'][sport]={'status':'UNAVAILABLE','rows':[],'fetchedAtEpoch':now.timestamp()}
    return {'status':'CONFIGURED','sports':state['sports'],'creditsUsed':state['creditsUsed'],'creditCap':cap,'refreshMinutes':interval//60},state

def match(forecasts,board,now,norm):
    out=[];counts={'observed':0,'matched':0}
    for sport,entry in board.get('sports',{}).items():
        elapsed=now.timestamp()-entry.get('fetchedAtEpoch',0)
        if elapsed<0 or elapsed>900:continue
        for line in entry.get('rows',[]):
            counts['observed']+=1
            if line.get('period')!='FULL' or str(line.get('odds_type','')).lower()!='standard':continue
            if not line.get('commence_time_reported') or not line.get('canonical_event_id'):continue
            try:
                start=datetime.fromisoformat(line['commence_time'].replace('Z','+00:00'))
                value=float(line['line']);age=float(line['age_seconds'])+elapsed
            except (ValueError,TypeError,KeyError):continue
            if not math.isfinite(value) or not math.isfinite(age) or not 0<=age<=900 or start<=now:continue
            prop=MARKETS.get(line.get('market_key'))
            candidates=[]
            for r in forecasts:
                if r['sport']!=sport or r['prop']!=prop or norm(r['player'])!=norm(line.get('player')):continue
                if abs((datetime.fromisoformat(r['startTime'].replace('Z','+00:00'))-start).total_seconds())>300:continue
                teams=[r.get('homeTeam'),r.get('awayTeam')]
                if sport=='NFL':teams=[NFL_NAMES.get(r['team']),NFL_NAMES.get(r['opponent'])]
                if None in teams or {norm(t) for t in teams}!={norm(line.get('home_team')),norm(line.get('away_team'))}:continue
                # The existing calibrated probability is only valid at this exact model line.
                model_line=r.get('modelLine',r['target']-.5)
                if r['direction']!='MORE' or abs(model_line-value)>1e-9:continue
                candidates.append(r)
            if len(candidates)!=1:continue
            r=dict(candidates[0],platform='Sleeper',platformLine=value,platformEventId=line['canonical_event_id'],actionable=True,offerObservedAt=datetime.fromtimestamp(now.timestamp()-age,timezone.utc).isoformat(),provider='ParlayAPI',payoutMultiplier=None)
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
