"""Freeze predictions for actual observed Sleeper thresholds, independently of live eligibility."""
import math
from collections import Counter,defaultdict
from datetime import timedelta
from platform_feed import match,market_prop,SPORTS
from validation import iso,finite,source_version
from nhl_adapter import exceedance,cached,get_json

MLB_VERSION='mlb-exact-line-empirical-v1'

def observed_valid(r,captured_at=None):
    try:
        capture=captured_at or iso(r['capturedAt'])
        return (r.get('forecastKind')=='SLEEPER_LINE' and r.get('observedPlatform')=='Sleeper' and
                bool(r.get('observedEventId')) and r.get('scheduleVerified') is True and
                finite(r.get('observedPlatformLine')) and r.get('modelLine')==r['observedPlatformLine'] and
                0<= (capture-iso(r['observedAt'])).total_seconds()<=900 and capture<iso(r['startTime']))
    except (KeyError,ValueError,TypeError,AttributeError):return False

def mlb_history(r,line,now,root,fetch):
    """Experimental same-team recent official game-log exceedance; never infers missing stats."""
    year=now.year;values={}
    for season in (year,year-1):
        doc=cached(root,f'mlb-lines-{r["playerId"]}-{season}',f'https://statsapi.mlb.com/api/v1/people/{r["playerId"]}/stats?stats=gameLog&group=hitting&season={season}&gameType=R',3600,now,fetch)
        for group in doc.get('stats',[]):
            for row in group.get('splits',[]):
                day=row.get('date','');stats=row.get('stat',{});gid=row.get('game',{}).get('gamePk')
                if not gid or row.get('gameType')!='R' or str(row.get('team',{}).get('id'))!=str(r.get('teamId')):continue
                try:date=iso(day+'T00:00:00Z')
                except (ValueError,TypeError):continue
                if not now-timedelta(days=400)<date<now.replace(hour=0,minute=0,second=0,microsecond=0):continue
                if not finite(stats.get('plateAppearances')) or stats['plateAppearances']<=0:continue
                keys={'Hits':'hits','Runs':'runs','RBI':'rbi','Bases':'totalBases','Walks':'baseOnBalls','Stolen Bases':'stolenBases','Home Runs':'homeRuns'}
                if r['prop']=='Hits + Runs + RBI':
                    parts=[stats.get(k) for k in ('hits','runs','rbi')];value=sum(parts) if all(finite(v) for v in parts) else None
                else:value=stats.get(keys.get(r['prop'],''))
                if finite(value):values[gid]=(date,value)
    rows=sorted(values.values(),reverse=True)[:60]
    if len(rows)<25 or rows[0][0]<now-timedelta(days=21):return None
    return {'probability':(sum(v>line for _,v in rows)+1)/(len(rows)+2),'projection':sum(v for _,v in rows)/len(rows),'samples':len(rows),'baselineVersion':MLB_VERSION}

def collect(forecasts,board,now,root,norm,fetch=get_json):
    templates=defaultdict(list)
    for r in forecasts:
        if r.get('scheduleVerified') and r.get('direction')=='MORE':templates[(r['sport'],r['prop'],norm(r.get('player')))].append(r)
    out={};rejected=Counter();history_cache={}
    for sport,entry in board.get('sports',{}).items():
        age=now.timestamp()-entry.get('fetchedAtEpoch',0)
        if not 0<=age<=900:continue
        for line in entry.get('rows',[]):
            prop=market_prop(sport,line.get('market_key'))
            if not prop:rejected['unsupported_market']+=1;continue
            value=line.get('line')
            try:value=float(value)
            except (ValueError,TypeError):rejected['unsupported_threshold']+=1;continue
            # Integer push settlement and fractional fantasy scores require separate models.
            if not math.isfinite(value) or not .5<=value<=999.5 or abs(value-(math.floor(value)+.5))>1e-9:
                rejected['unsupported_threshold']+=1;continue
            rows=templates.get((sport,prop,norm(line.get('player'))),[])
            # Pick an existing exact probability first; collapse repeated targets before identity resolution.
            unique={}
            for r in sorted(rows,key=lambda r:r.get('modelLine',r['target']-.5)!=value):unique.setdefault((str(r['gameId']),str(r['playerId'])),r)
            proxies=[dict(r,platformEligible=True,modelLine=value,target=value+.5) for r in unique.values()]
            resolved,counts=match(proxies,{'eligibleSports':list(SPORTS),'sports':{sport:dict(entry,rows=[line])}},now,norm)
            if not resolved:
                rejected.update(counts['excluded']);continue
            for probe in resolved:
                base=unique[(str(probe['gameId']),str(probe['playerId']))];candidate=dict(base)
                base_line=base.get('modelLine',base['target']-.5)
                if base_line==value:
                    p=base['sourceProbability'] if finite(base.get('sourceProbability')) else base['probability']
                elif sport in ('NBA','NHL') and base.get('distributionModel')=='COUNT_NB_V1' and finite(base.get('projection')) and base['projection']>0:
                    shape=base.get('distributionShape')
                    if shape is not None and (not finite(shape) or shape<=0):rejected['invalid_distribution']+=1;continue
                    p=exceedance(base['projection'],shape,math.floor(value)+1)
                elif sport=='MLB':
                    key=(base['playerId'],base['prop'],value)
                    try:
                        if key not in history_cache:history_cache[key]=mlb_history(base,value,now,root,fetch)
                        estimate=history_cache[key]
                    except Exception:rejected['history_source_unavailable']+=1;continue
                    if estimate is None:rejected['insufficient_history']+=1;continue
                    candidate.update(estimate);p=estimate['probability']
                else:rejected['no_exact_probability']+=1;continue
                if not finite(p) or not 0<p<1:rejected['invalid_probability']+=1;continue
                candidate.update(forecastKind='SLEEPER_LINE',observedPlatform='Sleeper',observedPlatformLine=value,
                    observedAt=probe['offerObservedAt'],observedEventId=probe['platformEventId'],observedOfferType=probe['platformOfferType'],
                    modelLine=value,target=value+.5,probability=p,sourceProbability=p,capturedAt=now.isoformat(),
                    probabilityStatus='UNVALIDATED_BASELINE',platformEligible=False,actionable=False,platform=None,platformLine=None,resultStatus='PENDING',
                    baselineNote='Prospective prediction at an observed Sleeper threshold; validation is separate from line identity.')
                candidate['id']='SLEEPER_LINE:'+':'.join(str(v) for v in (sport,candidate['gameId'],candidate['playerId'],prop,'MORE',value,source_version(candidate)))
                for k in ('offerId','provider','offerObservedAt','platformEventId','requiresPlatformReview','platformOfferType','payoutMultiplier'):candidate.pop(k,None)
                if observed_valid(candidate):out[candidate['id']]=candidate
    return list(out.values()),rejected
