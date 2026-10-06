"""NHL shots baseline from official regular-season logs and recent ice time.
Unvalidated estimates are recorded for prospective evaluation, never playable.
Coverage is bounded to eight current leading shooters per team, next 48 hours.
"""
import json, math, urllib.request, tempfile, os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

_CACHE_LOCK = Lock()
_CACHE_LOCKS = {}

API = 'https://api-web.nhle.com/v1/'
INJURIES = 'https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/injuries'

def get_json(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 (compatible; MultiSport-Pickem/0.4)'})
    with urllib.request.urlopen(req, timeout=25) as r: return json.load(r)

def cached(root, name, url, seconds, now, fetch=get_json):
    key=str(Path(root)/name)
    with _CACHE_LOCK:
        lock=_CACHE_LOCKS.setdefault(key,Lock())
    with lock:
        return _cached(root,name,url,seconds,now,fetch)

def _cached(root, name, url, seconds, now, fetch=get_json):
    path = Path(root)/'.runtime'/('nhl-'+name+'.json')
    if path.exists():
        item = json.loads(path.read_text())
        if 0 <= now.timestamp()-item['observedAt'] <= seconds: return item['data']
    data = fetch(url)  # Expired data is never silently reused on failure.
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False) as tmp:
        json.dump({'observedAt':now.timestamp(),'data':data},tmp)
        temp_name=tmp.name
    os.replace(temp_name,path)
    return data

def minutes(value):
    try:
        m,s = str(value).split(':')
        if int(m)<0 or not 0<=int(s)<60: return None
        return int(m)+int(s)/60
    except (ValueError,TypeError): return None

def number(value):
    if value is None or isinstance(value,bool): return None
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError): return None

def iso(value): return datetime.fromisoformat(value.replace('Z','+00:00'))
def full_name(team): return team['placeName']['default']+' '+team['commonName']['default']

def history(doc, season, team, cutoff):
    if int(doc.get('seasonId',0))!=season or doc.get('gameTypeId')!=2: return []
    rows={}
    for r in doc.get('gameLog',[]):
        try:
            day=datetime.strptime(r['gameDate'],'%Y-%m-%d').date()
            toi=minutes(r.get('toi')); shots=number(r.get('shots'))
            if day>=cutoff or (cutoff-day).days>400 or r.get('teamAbbrev')!=team: continue
            if toi is None or not 0<toi<=70 or shots is None or shots<0 or int(shots)!=shots: continue
            rows[r['gameId']] = dict(r, minutes=toi)
        except (KeyError,ValueError,TypeError): continue
    return sorted(rows.values(),key=lambda r:r['gameDate'],reverse=True)

def baseline(current, prior, now):
    if len(current)<2: return None,'insufficient_current_season'
    if (now.date()-datetime.strptime(current[0]['gameDate'],'%Y-%m-%d').date()).days>7:
        return None,'inactive_recently'
    all_rows=sorted({r['gameId']:r for r in current+prior}.values(),key=lambda r:r['gameDate'],reverse=True)[:60]
    if len(all_rows)<25: return None,'insufficient_history'
    recent=current[:5]
    expected=sum(r['minutes'] for r in recent)/len(recent)
    old_minutes=sum(r['minutes'] for r in all_rows)/len(all_rows)
    if not 12<=expected<=35 or not .75<=expected/old_minutes<=1.25:
        return None,'uncertain_ice_time'
    # Mean shot rate per minute; NB dispersion from historical counts scaled to
    # expected TOI. This is a descriptive baseline, not fitted matchup strength.
    projection=sum(r['shots'] for r in all_rows)/sum(r['minutes'] for r in all_rows)*expected
    if projection<=0: return None,'no_shot_support'
    adjusted=[r['shots']*expected/r['minutes'] for r in all_rows]
    mean=sum(adjusted)/len(adjusted)
    variance=sum((x-mean)**2 for x in adjusted)/(len(adjusted)-1)
    shape=projection**2/(variance-projection) if variance>projection else None
    return {'projection':projection,'expectedMinutes':expected,'samples':len(all_rows),
            'currentSeasonGames':len(current),'dispersionShape':shape},None

def exceedance(mean, shape, target):
    if shape is None:
        p=math.exp(-mean); total=p
        for k in range(1,target): p*=mean/k; total+=p
    else:
        q=shape/(shape+mean); p=math.exp(shape*math.log(q)); total=p
        for k in range(1,target): p*=(shape+k-1)/k*(1-q); total+=p
    return max(.001,min(.999,1-total))

def collect(now, root, model, corrected, norm, fetch=get_json):
    today=now.astimezone(ZoneInfo('America/Chicago')).date()
    schedule=cached(root,'schedule-'+today.isoformat(),API+'schedule/'+today.isoformat(),900,now,fetch)
    games=[g for d in schedule.get('gameWeek',[]) for g in d.get('games',[])
           if g.get('gameType')==2 and g.get('gameState') in ('FUT','PRE')
           and g.get('gameScheduleState')=='OK' and now<iso(g['startTimeUTC'])<=now+timedelta(hours=48)]
    injuries=cached(root,'injuries',INJURIES,900,now,fetch)
    if injuries.get('status')!='success' or not isinstance(injuries.get('injuries'),list):
        raise ValueError('Unavailable injury source')
    if not -300<=(now-iso(injuries['timestamp'])).total_seconds()<=3600:
        raise ValueError('Stale injury source')
    excluded={(norm(t['displayName']),norm(i['athlete']['displayName']))
              for t in injuries['injuries'] for i in t.get('injuries',[])}
    rejected=Counter(); jobs=[]
    def team_job(item):
        g,side=item; team=g[side]; abbr=team['abbrev']; season=int(g['season'])
        jobs=[];rejected=Counter()
        try:
            roster=cached(root,'roster-'+abbr+'-'+str(season),API+f'roster/{abbr}/{season}',3600,now,fetch)
            club=cached(root,'club-'+abbr+'-'+str(season),API+f'club-stats/{abbr}/{season}/2',3600,now,fetch)
            if int(club.get('season',0))!=season or club.get('gameType')!=2: raise ValueError('Wrong season')
            ids={p['id']:p for kind in ('forwards','defensemen') for p in roster.get(kind,[])}
            skaters=[p for p in club.get('skaters',[]) if p.get('playerId') in ids and number(p.get('gamesPlayed')) and p['gamesPlayed']>=2]
            skaters.sort(key=lambda p:-(p.get('shots',0)/p['gamesPlayed']))
            for p in skaters[:8]:
                identity=ids[p['playerId']]
                name=identity['firstName']['default']+' '+identity['lastName']['default']
                if (norm(full_name(team)),norm(name)) in excluded:
                    rejected['injury_report']+=1;continue
                jobs.append((g,side,identity,name))
        except Exception: rejected['unavailable_team_source']+=1
        return jobs,rejected
    team_items={(g['id'],side):(g,side) for g in games for side in ('homeTeam','awayTeam')}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for candidates,reasons in pool.map(team_job,team_items.values()):
            jobs.extend(candidates);rejected.update(reasons)
    def player_job(item):
        g,side,identity,name=item; team=g[side]; season=int(g['season']); pid=identity['id']
        try:
            cur=cached(root,f'log-{pid}-{season}',API+f'player/{pid}/game-log/{season}/2',3600,now,fetch)
            previous=season-10001
            old=cached(root,f'log-{pid}-{previous}',API+f'player/{pid}/game-log/{previous}/2',86400,now,fetch)
            cutoff=min(today,iso(g['startTimeUTC']).date())
            current=history(cur,season,team['abbrev'],cutoff)
            prior=history(old,previous,team['abbrev'],cutoff)
            estimate,reason=baseline(current,prior,now)
            if reason: return [],reason
            opponent=g['awayTeam' if side=='homeTeam' else 'homeTeam']
            rows=[]
            for target in (1,2,3,4,5):
                r={'id':f"NHL:{g['id']}:{pid}:Shots on Goal:MORE:{target}", 'sport':'NHL','gameId':g['id'],
                   'playerId':pid,'player':name,'team':team['abbrev'],'opponent':opponent['abbrev'],
                   'homeTeam':full_name(g['homeTeam']),'awayTeam':full_name(g['awayTeam']),
                   'season':season,'prop':'Shots on Goal','direction':'MORE','target':target,'modelLine':target-.5,
                   'projection':estimate['projection'],'sourceProbability':exceedance(estimate['projection'],estimate['dispersionShape'],target),
                   'samples':estimate['samples'],'currentSeasonGames':estimate['currentSeasonGames'],
                   'expectedPlayingTime':estimate['expectedMinutes'],'playingTimeUnit':'minutes on ice',
                   'startTime':g['startTimeUTC'],'capturedAt':now.isoformat(),'lineupStatus':'Roster verified; lineup unconfirmed',
                   'probabilityStatus':'UNVALIDATED_BASELINE','baselineVersion':'nhl-shots-toi-nb-1',
                   'platformEligible':False,'platformLine':None,'platform':None,'actionable':False,'resultStatus':'PENDING',
                   'modelVersion':model['version']}
                r['probability']=corrected(r,model);rows.append(r)
            return rows,None
        except Exception: return [],'unavailable_player_source'
    out=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for rows,reason in pool.map(player_job,jobs):
            out.extend(rows)
            if reason: rejected[reason]+=1
    unavailable=not out and (bool(jobs) and rejected['unavailable_player_source']==len(jobs) or not jobs and rejected['unavailable_team_source']>0)
    return out,{'status':'UNAVAILABLE' if unavailable else 'BASELINE_FORECASTS','sourceStatus':'UNAVAILABLE' if unavailable else 'CURRENT','verifiedRows':len(out),
                'gamesChecked':len(games),'modelVersion':'nhl-shots-toi-nb-1','validationStatus':'COLLECTING_PROSPECTIVE_RESULTS',
                'coverageStatus':'PARTIAL' if rejected['unavailable_team_source'] or rejected['unavailable_player_source'] else 'VERIFIED_POOL',
                'coverage':'Top eight current shooters per team; regular-season games within 48 hours',
                'sourceUpdatedAt':now.isoformat()},rejected

def grade(ledger, now, root, fetch=get_json):
    boxes={}
    for r in ledger:
        if r['sport']!='NHL' or r.get('resultStatus')!='PENDING' or iso(r['startTime'])>now: continue
        gid=r['gameId']
        if gid not in boxes: boxes[gid]=cached(root,'box-'+str(gid),API+f'gamecenter/{gid}/boxscore',900,now,fetch)
        box=boxes[gid]
        if box.get('id')!=gid or box.get('season')!=r['season'] or box.get('gameType')!=2 or box.get('gameState') not in ('FINAL','OFF'): continue
        side=next((s for s in ('homeTeam','awayTeam') if box.get(s,{}).get('abbrev')==r['team']),None)
        opponent=box.get('awayTeam' if side=='homeTeam' else 'homeTeam',{}).get('abbrev')
        if side is None or opponent!=r['opponent']: continue
        group=box.get('playerByGameStats',{}).get(side,{})
        players=[p for kind in ('forwards','defense') for p in group.get(kind,[]) if p.get('playerId')==r['playerId']]
        if len(players)!=1: continue  # No verified player row: never infer a loss or a DNP.
        p=players[0]; toi=minutes(p.get('toi')); shots=number(p.get('sog'))
        if toi==0:
            r.update(resultStatus='VOID',voidReason='No ice time');continue
        if toi is None or shots is None or shots<0: continue
        r.update(resultStatus='GRADED',actual=shots,outcome=int(shots>=r['target']),gradedAt=now.isoformat())
