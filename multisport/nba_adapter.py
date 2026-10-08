"""ESPN NBA regular-season count baselines with recent minutes and injury gates.
Preseason is excluded. All NBA baselines remain ineligible for platform slips.
"""
import math
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from nhl_adapter import get_json,cached,iso,number,minutes,exceedance

API='https://site.api.espn.com/apis/site/v2/sports/basketball/nba/'
LOG='https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba/athletes/{pid}/gamelog?season={season}'
STATS={'Points':('points','PTS'), 'Rebounds':('totalRebounds','REB'),
       'Assists':('assists','AST'), '3-Pointers Made':('threePointFieldGoalsMade-threePointFieldGoalsAttempted','3PT')}
TARGETS={'Points':(10,15,20,25,30,35),'Rebounds':(2,4,6,8,10,12),'Assists':(2,4,6,8,10),'3-Pointers Made':(1,2,3,4,5)}

def playing_minutes(value):
    return minutes(value) if ':' in str(value) else number(value)

def stat_value(prop,value):
    if prop=='3-Pointers Made' and isinstance(value,str) and '-' in value:
        value=value.split('-')[0]
    v=number(value)
    return v if v is not None and v>=0 and int(v)==v else None

def history(doc,season,team,now):
    seasons=[f.get('value') for f in doc.get('filters',[]) if f.get('name')=='season']
    if seasons!=[str(season)]: return []
    labels=doc.get('names',[]); out={}
    for section in doc.get('seasonTypes',[]):
        if section.get('displayName')!=f'{season-1}-{str(season)[-2:]} Regular Season' or section.get('displayTeam')!=team['abbreviation']:continue
        for category in section.get('categories',[]):
            for r in category.get('events',[]):
                try:
                    event=doc['events'][r['eventId']]; started=iso(event['gameDate'])
                    if str(team['id']) not in (str(event['homeTeamId']),str(event['awayTeamId'])) or now-started<timedelta(hours=4) or (now-started).days>400 or event.get('gameResult') not in ('W','L'):continue
                    if len(r['stats'])!=len(labels):continue
                    stats=dict(zip(labels,r['stats'])); toi=playing_minutes(stats.get('minutes'))
                    if toi is None or not 0<toi<=70:continue
                    values={prop:stat_value(prop,stats.get(name)) for prop,(name,_) in STATS.items()}
                    if any(v is None for v in values.values()):continue
                    out[r['eventId']]={'gameId':r['eventId'],'startTime':event['gameDate'],'minutes':toi,**values}
                except (KeyError,TypeError,ValueError):continue
    return sorted(out.values(),key=lambda r:r['startTime'],reverse=True)

def baseline(current,prior,prop,now):
    if len(current)<3:return None,'insufficient_current_season'
    if (now-iso(current[0]['startTime'])).days>7:return None,'inactive_recently'
    rows=sorted({r['gameId']:r for r in current+prior}.values(),key=lambda r:r['startTime'],reverse=True)[:60]
    if len(rows)<25:return None,'insufficient_history'
    recent=current[:5];expected=sum(r['minutes'] for r in recent)/len(recent)
    old=sum(r['minutes'] for r in rows)/len(rows)
    if not 15<=expected<=40 or not .75<=expected/old<=1.25:return None,'uncertain_minutes'
    projection=sum(r[prop] for r in rows)/sum(r['minutes'] for r in rows)*expected
    if projection<=0:return None,'no_stat_support'
    adjusted=[r[prop]*expected/r['minutes'] for r in rows]; mean=sum(adjusted)/len(adjusted)
    variance=sum((x-mean)**2 for x in adjusted)/(len(adjusted)-1)
    shape=projection**2/(variance-projection) if variance>projection else None
    return {'projection':projection,'expectedMinutes':expected,'samples':len(rows),'shape':shape},None

def collect(now,root,model,corrected,norm,fetch=get_json):
    today=now.astimezone(ZoneInfo('America/Chicago')).date();games={}; preseason=0
    for offset in range(3):
        day=(today+timedelta(days=offset)).strftime('%Y%m%d')
        source=cached(root,'nba-schedule-'+day,API+'scoreboard?dates='+day,900,now,fetch)
        if not isinstance(source.get('events'),list):raise ValueError('Invalid schedule')
        for g in source['events']:
            if g.get('season',{}).get('type')==1:preseason+=1;continue
            if g.get('season',{}).get('type')!=2 or g.get('status',{}).get('type',{}).get('state')!='pre':continue
            if now<iso(g['date'])<=now+timedelta(hours=48):games[g['id']]=g
    status={'status':'BASELINE_FORECASTS' if games else 'PRESEASON_EXCLUDED' if preseason else 'WAITING_FOR_GAMES',
            'sourceStatus':'CURRENT','verifiedRows':0,'gamesChecked':len(games),'preseasonGamesExcluded':preseason,
            'validationStatus':'COLLECTING_PROSPECTIVE_RESULTS','modelVersion':'nba-counts-minutes-nb-1',
            'coverage':'Active roster candidates; regular-season games within 48 hours', 'sourceUpdatedAt':now.isoformat()}
    if not games:return [],status,{}
    injuries=cached(root,'nba-injuries',API+'injuries',900,now,fetch)
    if injuries.get('status')!='success' or not isinstance(injuries.get('injuries'),list) or not -300<=(now-iso(injuries['timestamp'])).total_seconds()<=3600:
        raise ValueError('Invalid injury source')
    excluded={(str(t['id']),norm(i['athlete']['displayName'])) for t in injuries['injuries'] for i in t.get('injuries',[])}
    jobs=[];rejected=Counter()
    for g in games.values():
        competitors=g['competitions'][0]['competitors']
        if len(competitors)!=2:rejected['ambiguous_game']+=1;continue
        for c in competitors:
            team=c['team'];season=int(g['season']['year'])
            try:
                roster=cached(root,'nba-roster-'+str(team['id']),API+f"teams/{team['id']}/roster",3600,now,fetch)
                if str(roster.get('team',{}).get('id'))!=str(team['id']) or int(roster.get('season',{}).get('year',0))!=season:raise ValueError('Wrong roster season/team')
                for player in roster.get('athletes',[]):
                    if player.get('status',{}).get('type')!='active' or player.get('injuries') or (str(team['id']),norm(player['displayName'])) in excluded:
                        rejected['unavailable_player']+=1;continue
                    jobs.append((g,c,player))
            except Exception:rejected['unavailable_team_source']+=1
    def player_job(item):
        g,c,player=item;team=c['team'];pid=player['id'];season=int(g['season']['year'])
        try:
            current=history(cached(root,f'nba-log-{pid}-{season}',LOG.format(pid=pid,season=season),3600,now,fetch),season,team,now)
            prior=history(cached(root,f'nba-log-{pid}-{season-1}',LOG.format(pid=pid,season=season-1),86400,now,fetch),season-1,team,now)
            home=next(x['team'] for x in g['competitions'][0]['competitors'] if x['homeAway']=='home')
            away=next(x['team'] for x in g['competitions'][0]['competitors'] if x['homeAway']=='away')
            opponent=away if c['homeAway']=='home' else home;rows=[];reasons=Counter()
            for prop,targets in TARGETS.items():
                estimate,reason=baseline(current,prior,prop,now)
                if reason:reasons[reason]+=1;continue
                for target in targets:
                    r={'id':f"NBA:{g['id']}:{pid}:{prop}:MORE:{target}",'sport':'NBA','gameId':g['id'],'playerId':pid,
                       'teamId':str(team['id']),'opponentId':str(opponent['id']),'player':player['displayName'],
                       'team':team['abbreviation'],'opponent':opponent['abbreviation'],'homeTeam':home['displayName'],'awayTeam':away['displayName'],
                       'season':season,'prop':prop,'direction':'MORE','target':target,'modelLine':target-.5,
                       'projection':estimate['projection'],'sourceProbability':exceedance(estimate['projection'],estimate['shape'],target),
                       'samples':estimate['samples'],'currentSeasonGames':len(current),'expectedPlayingTime':estimate['expectedMinutes'],
                       'playingTimeUnit':'minutes','startTime':g['date'],'capturedAt':now.isoformat(),'lineupStatus':'Active roster; lineup unconfirmed',
                       'probabilityStatus':'UNVALIDATED_BASELINE','baselineVersion':'nba-counts-minutes-nb-1','modelVersion':model['version'],
                       'platformEligible':False,'platformLine':None,'platform':None,'actionable':False,'resultStatus':'PENDING'}
                    r['probability']=corrected(r,model);rows.append(r)
            return rows,reasons
        except Exception:return [],Counter({'unavailable_player_source':1})
    out=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        for rows,reasons in pool.map(player_job,jobs):out.extend(rows);rejected.update(reasons)
    status['verifiedRows']=len(out)
    return out,status,rejected

def grade(ledger,now,root,fetch=get_json):
    from result_jobs import load_results
    pending=[r for r in ledger if r['sport']=='NBA' and r.get('resultStatus')=='PENDING' and iso(r['startTime'])<=now]
    summaries,health=load_results((r['gameId'] for r in pending),lambda gid:cached(root,'nba-summary-'+str(gid),API+'summary?event='+str(gid),900,now,fetch))
    for r in pending:
        gid=r['gameId']
        if gid not in summaries:continue
        summary=summaries[gid];header=summary.get('header',{})
        games=header.get('competitions',[])
        if str(header.get('id'))!=str(gid) or header.get('season',{}).get('year')!=r['season'] or header.get('season',{}).get('type')!=2 or len(games)!=1 or not games[0].get('status',{}).get('type',{}).get('completed'):continue
        ids={str(c['team']['id']) for c in games[0].get('competitors',[])}
        if ids!={r['teamId'],r['opponentId']}:continue
        found=[]
        for t in summary.get('boxscore',{}).get('players',[]):
            if str(t.get('team',{}).get('id'))!=r['teamId']:continue
            for section in t.get('statistics',[]):
                for player in section.get('athletes',[]):
                    if str(player.get('athlete',{}).get('id'))==str(r['playerId']):found.append((section,player))
        if len(found)!=1:continue
        section,p=found[0]
        if p.get('didNotPlay') is True:r.update(resultStatus='VOID',voidReason='Did not play');continue
        labels=section.get('labels',[]);values=p.get('stats',[])
        if len(labels)!=len(values):continue
        stats=dict(zip(labels,values));toi=playing_minutes(stats.get('MIN'))
        if toi==0:r.update(resultStatus='VOID',voidReason='No playing time');continue
        value=stat_value(r['prop'],stats.get(STATS[r['prop']][1]))
        if toi is None or value is None:continue
        r.update(resultStatus='GRADED',actual=value,outcome=int(value>=r['target']),gradedAt=now.isoformat())
    return health
