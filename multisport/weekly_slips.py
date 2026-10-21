"""Freeze prospective model slips, fill three slots per size/week, grade without hindsight."""
from copy import deepcopy
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import math
from platform_feed import diverse_slips
from validation import graded as valid_grade

SIZES=(2,3,4,5,6,8)
COUNT=3
CT=ZoneInfo('America/Chicago')

def instant(value):
    parsed=datetime.fromisoformat(value.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('Timezone required')
    return parsed

def week_key(now):return now.astimezone(CT).strftime('%G-W%V')
def signature(legs):return tuple(sorted(r['forecastId'] for r in legs))

def update(saved,forecasts,ledger,sports,now):
    saved=deepcopy(saved)
    # Identity includes the same target as the frozen leg. Never substitute another prop/line.
    results={}
    for r in ledger:results.setdefault(r.get('id'),r)
    for slip in saved:
        for leg in slip['legs']:
            if leg['status'] in ('HIT','MISS','VOID'):continue
            r=results.get(leg['forecastId'])
            if not r:continue
            identity=('sport','gameId','playerId','prop','direction')
            if any(str(r.get(k))!=str(leg.get(k)) for k in identity):continue
            rline=r.get('modelLine',r.get('target',.5)-.5)
            if rline!=leg['modelLine']:continue
            if r.get('resultStatus')=='VOID':
                leg.update(status='VOID',voidReason=r.get('voidReason',''));continue
            if valid_grade(r):
                # Re-evaluate the frozen threshold; no current probabilities are read.
                hit=r['actual']>leg['modelLine'] if leg.get('usesModelLine') else r['actual']>=leg['target']
                leg.update(status='HIT' if hit else 'MISS',actual=r['actual'],gradedAt=r['gradedAt'])
        counts={s:sum(r['status']==s for r in slip['legs']) for s in ('HIT','MISS','VOID','PENDING')}
        slip.update(hits=counts['HIT'],misses=counts['MISS'],voids=counts['VOID'],pending=counts['PENDING'])
        slip['status']=('IN_PROGRESS' if counts['HIT']+counts['MISS']+counts['VOID'] else 'PENDING') if counts['PENDING'] else 'MISSED' if counts['MISS'] else 'VOIDED' if counts['VOID'] else 'ALL_HIT'
        slip['allHit']=counts['HIT']==slip['size'] and not counts['MISS']+counts['VOID']+counts['PENDING']
    week=week_key(now)
    pool=[]
    for r in forecasts:
        try:
            p=r['probability'];start=instant(r['startTime']);capture=instant(r['capturedAt'])
            if isinstance(p,bool) or not math.isfinite(p) or not 0<p<1:continue
            if start<=now or capture>now or (now-capture).total_seconds()>2700:continue
            if week_key(start)!=week or capture>=start:continue
            if not r.get('scheduleVerified') or sports.get(r['sport'],{}).get('sourceStatus')!='CURRENT':continue
            if r.get('direction')!='MORE' or any(r.get(k) is None for k in ('id','gameId','playerId','target')):continue
            pool.append(r)
        except (KeyError,ValueError,TypeError,AttributeError):continue
    # More than three candidates allows a later refresh to fill remaining slots
    # while excluding signatures already frozen earlier in the week.
    for size in SIZES:
        existing=[s for s in saved if s['week']==week and s['size']==size]
        seen={signature(s['legs']) for s in existing}
        for candidate in diverse_slips(pool,size,COUNT-len(existing),existing):
            if len(existing)>=COUNT:break
            legs=[]
            for r in candidate['legs']:
                leg={k:r.get(k) for k in ('sport','gameId','playerId','player','team','opponent','prop','direction','target','startTime','probability','sourceProbability','modelVersion','baselineVersion','upstreamModelVersion','probabilityStatus','platformEligible')}
                leg.update(forecastId=r['id'],modelLine=r.get('modelLine',r['target']-.5),usesModelLine='modelLine' in r,status='PENDING')
                legs.append(leg)
            key=signature(legs)
            if key in seen:continue
            slot=len(existing)+1
            slip=dict(id=f'{week}:{size}:{slot}',week=week,size=size,slot=slot,capturedAt=now.isoformat(),kind='MODEL_TEST',platform=None,actionable=False,probability=candidate['probability'],rankingMethod=candidate['rankingMethod'],searchComplete=candidate['searchComplete'],status='PENDING',allHit=False,hits=0,misses=0,voids=0,pending=size,legs=legs)
            saved.append(slip);existing.append(slip);seen.add(key)
    summary=[]
    for w in sorted({s['week'] for s in saved}|{week},reverse=True):
        for size in SIZES:
            rs=[s for s in saved if s['week']==w and s['size']==size]
            summary.append(dict(week=w,size=size,target=COUNT,saved=len(rs),allHit=sum(s['allHit'] for s in rs),missed=sum(s['status']=='MISSED' for s in rs),voided=sum(s['status']=='VOIDED' for s in rs),pending=sum(s['pending']>0 for s in rs)))
    return saved,dict(currentWeek=week,kind='MODEL_TEST',summary=summary,slips=saved)
