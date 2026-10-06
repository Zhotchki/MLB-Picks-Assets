"""Prospective model-target validation. Reports evidence; never enables offers.
Separate source/model versions and split entire events chronologically.
Repeated thresholds do not count as additional player-game support.
"""
import math
from collections import defaultdict,Counter
from datetime import datetime
from zoneinfo import ZoneInfo

MINIMUMS={'trainingPlayerGames':200,'holdoutPlayerGames':100,'trainingGames':25,
          'holdoutGames':10,'trainingDays':7,'holdoutDays':3}
DEFAULTS={'NBA':['Points','Rebounds','Assists','3-Pointers Made'],'NHL':['Shots on Goal']}

def iso(v):
    if not isinstance(v,str):raise ValueError('Timestamp required')
    parsed=datetime.fromisoformat(v.replace('Z','+00:00'))
    if parsed.tzinfo is None:raise ValueError('Timestamp timezone required')
    return parsed
def finite(v):return isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v)
def player_game(r):return (r['sport'],str(r['gameId']),str(r['playerId']))
def event(r):return (r['sport'],str(r['gameId']))
def source_version(r):return str(r.get('baselineVersion') or r.get('upstreamModelVersion') or 'upstream-unspecified')
def key(r):return (r['sport'],r['prop'],r['direction'],source_version(r),str(r.get('modelVersion','unspecified')))

def pregame(r):
    try:
        return bool(r['id']) and all(r.get(k) is not None for k in ('sport','gameId','playerId','prop','direction')) and iso(r['capturedAt'])<iso(r['startTime']) and finite(r['probability']) and 0<r['probability']<1
    except (KeyError,ValueError,TypeError,AttributeError):return False

def graded(r):
    if r.get('resultStatus')!='GRADED' or r.get('outcome') not in (0,1) or not finite(r.get('actual')):return False
    try:
        if iso(r['gradedAt'])<iso(r['startTime']):return False
        if r['direction']!='MORE':return False
        if finite(r.get('modelLine')):outcome=int(r['actual']>r['modelLine'])
        elif finite(r.get('target')):outcome=int(r['actual']>=r['target'])
        else:return False
        return outcome==r['outcome']
    except (KeyError,ValueError,TypeError):return False

def support(rows):
    return {'forecasts':len(rows),'playerGames':len({player_game(r) for r in rows}),
            'games':len({event(r) for r in rows}),'days':len({iso(r['startTime']).astimezone(ZoneInfo('America/Chicago')).date() for r in rows})}

def score(rows,predict=lambda r:r['probability']):
    if not rows:return {'brier':None,'logLoss':None,'meanProbability':None,'targetHitRate':None,'calibrationBias':None}
    players=defaultdict(list)
    for r in rows:
        p=max(1e-12,min(1-1e-12,predict(r)));y=r['outcome']
        players[player_game(r)].append(((p-y)**2,-y*math.log(p)-(1-y)*math.log(1-p),p,y,p-y))
    games=defaultdict(list)
    for pg,values in players.items():games[pg[:2]].append([sum(v[i] for v in values)/len(values) for i in range(5)])
    averages=[[sum(v[i] for v in values)/len(values) for i in range(5)] for values in games.values()]
    values=[sum(v[i] for v in averages)/len(averages) for i in range(5)]
    return dict(zip(('brier','logLoss','meanProbability','targetHitRate','calibrationBias'),values))

def projection_errors(rows):
    players={}
    for r in rows:
        if finite(r.get('projection')):players.setdefault(player_game(r),r['projection']-r['actual'])
    if not players:return {'playerGames':0,'mae':None,'rmse':None,'bias':None}
    values=list(players.values())
    return {'playerGames':len(values),'mae':sum(abs(v) for v in values)/len(values),
            'rmse':math.sqrt(sum(v*v for v in values)/len(values)),'bias':sum(values)/len(values)}

def chronological(rows):
    games=sorted({(iso(r['startTime']),event(r)) for r in rows})
    cut=int(len(games)*.8);train_ids={g for _,g in games[:cut]}
    return ([r for r in rows if event(r) in train_ids],[r for r in rows if event(r) not in train_ids])

def holdout(rows):
    train,test=chronological(rows);a,b=support(train),support(test)
    result={'status':'COLLECTING_SEPARATE_GAMES','training':a,'holdout':b,'minimums':MINIMUMS,
            'trainingThrough':max((r['startTime'] for r in train),default=None),
            'holdoutFrom':min((r['startTime'] for r in test),default=None),'forecastScores':None,'referenceScores':None}
    if any(a[k]<MINIMUMS['training'+k[0].upper()+k[1:]] or b[k]<MINIMUMS['holdout'+k[0].upper()+k[1:]] for k in ('playerGames','games','days')):return result
    # Constant-per-target reference fitted only on training outcomes. It is a
    # skill comparator, not a bookmaker probability or payout.
    buckets=defaultdict(list)
    def threshold(r):return (r.get('modelLine'),r.get('target'))
    for r in train:buckets[threshold(r)].append(r)
    if any(threshold(r) not in buckets or len({player_game(v) for v in buckets[threshold(r)]})<30 for r in test):
        result['status']='INSUFFICIENT_TRAINING_FOR_TARGETS';return result
    reference={}
    for k,values in buckets.items():
        n=len({player_game(r) for r in values})
        reference[k]=(score(values)['targetHitRate']*n+2)/(n+4)
    trial=score(test);base=score(test,lambda r:reference[threshold(r)])
    result.update(status='REVIEWABLE_HOLDOUT',forecastScores=trial,referenceScores=base,
                  brierImprovement=base['brier']-trial['brier'],logLossImprovement=base['logLoss']-trial['logLoss'],
                  beatsReference=trial['brier']<base['brier'] and trial['logLoss']<base['logLoss'])
    return result

def report(ledger):
    buckets=defaultdict(list);seen=set();invalid=0;duplicate=0
    for r in sorted(ledger,key=lambda r:str(r.get('capturedAt',''))):
        if not pregame(r):invalid+=1;continue
        if r['id'] in seen:duplicate+=1;continue
        seen.add(r['id']);buckets[key(r)].append(r)
    groups=[];sport_rows=defaultdict(list)
    for k,rows in sorted(buckets.items()):
        sport,prop,direction,source,model=k;completed=[r for r in rows if graded(r)]
        invalid_results=sum(r.get('resultStatus')=='GRADED' and not graded(r) for r in rows)
        projection=projection_errors(completed);review=holdout(completed)
        groups.append({'sport':sport,'prop':prop,'direction':direction,'sourceVersion':source,'modelVersion':model,
                       'status':'COLLECTING_RESULTS' if not completed else review['status'],
                       'recorded':support(rows),'graded':support(completed),'pending':sum(r.get('resultStatus')=='PENDING' for r in rows),
                       'void':sum(r.get('resultStatus')=='VOID' for r in rows),'invalidResults':invalid_results,
                       'scores':score(completed),'projectionErrors':projection,'review':review,'enablesPlayableOffers':False})
        sport_rows[sport].extend(rows)
    for sport,props in DEFAULTS.items():
        for prop in props:
            if not any(g['sport']==sport and g['prop']==prop for g in groups):
                groups.append({'sport':sport,'prop':prop,'status':'WAITING_FOR_FORECASTS','recorded':support([]),
                               'graded':support([]),'pending':0,'void':0,'invalidResults':0,'scores':score([]),
                               'projectionErrors':projection_errors([]),'review':holdout([]),'enablesPlayableOffers':False})
    sports={s:{'recorded':support(sport_rows[s]),'graded':support([r for r in sport_rows[s] if graded(r)]),
               'pending':sum(r.get('resultStatus')=='PENDING' for r in sport_rows[s]),
               'void':sum(r.get('resultStatus')=='VOID' for r in sport_rows[s])} for s in ('MLB','NFL','NBA','NHL')}
    return {'version':'prospective-targets-1','sports':sports,'groups':groups,'invalidForecasts':invalid,'duplicateForecasts':duplicate,
            'method':'Frozen pregame probabilities; versions separated; later whole-game holdout; scores balanced by player-game then event.',
            'limitation':'Model-target accuracy is not platform wager win rate. Reviewable support is not proof of calibration, betting edge, or generalization. Reports never enable baseline offers.'}
