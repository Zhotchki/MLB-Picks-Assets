"""Publish read-only, credential-free Google Sheets views of existing app data."""
import csv,json,io,math
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
RESULT_LIMIT=5000

def local_time(value):
    if not value:return ''
    try:return datetime.fromisoformat(value.replace('Z','+00:00')).astimezone(ZoneInfo('America/Chicago')).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError,TypeError,AttributeError):return ''

def cell(value):
    if value is None:return ''
    if isinstance(value,bool):return 'Yes' if value else 'No'
    if isinstance(value,float) and not math.isfinite(value):return ''
    if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')):return "'"+value
    return value

def line(row):return row.get('modelLine',row.get('target',.5)-.5)

def tables(data,ledger):
    stamp=local_time(data.get('updatedAt'))
    forecasts=[['Sport','Player','Team','Opponent','Prop','Direction','Model line','Probability','Projection','History games','Game time CT','Probability status','Platform eligible','Source version','Captured CT']]
    for r in data.get('picks',[]):
        forecasts.append([r.get('sport'),r.get('player'),r.get('team'),r.get('opponent'),r.get('prop'),r.get('direction'),line(r),r.get('probability'),r.get('projection'),r.get('samples'),local_time(r.get('startTime')),r.get('probabilityStatus'),r.get('platformEligible',True),r.get('baselineVersion') or r.get('upstreamModelVersion'),local_time(r.get('capturedAt'))])
    offers=[['Sport','Player','Team','Prop','Direction','Platform line','Probability','Game time CT','Line observed CT','Review required','Offer type','Payout multiplier']]
    for r in data.get('offers',[]):
        offers.append([r.get('sport'),r.get('player'),r.get('team'),r.get('prop'),r.get('direction'),r.get('platformLine'),r.get('probability'),local_time(r.get('startTime')),local_time(r.get('offerObservedAt')),r.get('requiresPlatformReview'),r.get('platformOfferType'),r.get('payoutMultiplier')])
    slips=[['Slip size','Rank','Leg','Sport','Player','Prop','Direction','Line','Leg probability','Slip probability','Game time CT','Line observed CT','Review required','Ranking complete']]
    for size,groups in data.get('slips',{}).items():
        for rank,slip in enumerate(groups,1):
            for n,r in enumerate(slip.get('legs',[]),1):
                slips.append([int(size),rank,n,r.get('sport'),r.get('player'),r.get('prop'),r.get('direction'),r.get('platformLine'),r.get('probability'),slip.get('probability'),local_time(r.get('startTime')),local_time(r.get('offerObservedAt')),r.get('requiresPlatformReview'),slip.get('searchComplete')])
    settled=sorted((r for r in ledger if r.get('resultStatus') in ('GRADED','VOID')),key=lambda r:(r.get('startTime',''),r.get('id','')),reverse=True)
    results=[['Sport','Player','Team','Prop','Direction','Model line','Frozen probability','Actual','Outcome','Status','Game time CT','Source version']]
    for r in settled[:RESULT_LIMIT]:
        results.append([r.get('sport'),r.get('player'),r.get('team'),r.get('prop'),r.get('direction'),line(r),r.get('probability'),r.get('actual'),r.get('outcome'),r.get('resultStatus'),local_time(r.get('startTime')),r.get('baselineVersion') or r.get('upstreamModelVersion')])
    performance=[['Sport','Prop','Direction','Source version','Validation status','Graded forecasts','Player games','Separate games','Brier score','Log loss','Mean probability','Target hit rate','Holdout player games','Holdout games','All lines beat reference']]
    for g in data.get('validation',{}).get('groups',[]):
        scores=g.get('scores') or {};review=g.get('review') or {};hold=review.get('holdout') or {};graded=g.get('graded') or {}
        performance.append([g.get('sport'),g.get('prop'),g.get('direction'),g.get('sourceVersion'),g.get('status'),graded.get('forecasts'),graded.get('playerGames'),graded.get('games'),scores.get('brier'),scores.get('logLoss'),scores.get('meanProbability'),scores.get('targetHitRate'),hold.get('playerGames'),hold.get('games'),review.get('allTargetsBeatReference')])
    status=[['Metric','Value','Detail'],['Feed updated CT',stamp,'Compare this timestamp with current time; Sheets can lag the app.'],['App version',data.get('version'),''],['Model version',data.get('model',{}).get('version'),''],['Saved forecasts',data.get('results',{}).get('recorded'),'Full immutable ledger'],['Graded forecasts',data.get('results',{}).get('graded'),'Full history; model targets, not wager results'],['Voided forecasts',data.get('results',{}).get('void'),''],['Current forecasts',len(data.get('picks',[])),'Snapshot; check game time and source freshness'],['Matched offers',len(data.get('offers',[])),'Snapshot only; usable for at most 15 minutes from observation'],['Slip status',data.get('slipStatus'),'Use the live app to check current line eligibility'],['Next board check CT',local_time(data.get('platformFeed',{}).get('nextRefreshAt')),'Earliest planned check; may be delayed'],['Board check reason',data.get('platformFeed',{}).get('refreshReason'),''],['Monthly credits used',data.get('platformFeed',{}).get('creditsUsed'),''],['Monthly credit cap',data.get('platformFeed',{}).get('creditCap'),''],['Results shown',min(len(settled),RESULT_LIMIT),f'Latest {RESULT_LIMIT:,} settled forecast rows; full history stays in app ledger'],['Total settled forecasts',len(settled),'Includes graded and void'],['Last weekly review',data.get('model',{}).get('lastReviewWeek'),''],['Weekly decision',data.get('model',{}).get('review',{}).get('status'),'']]
    for sport,s in data.get('sports',{}).items():status.append([sport+' source',s.get('sourceStatus'),s.get('status')])
    weekly=[['Week','Slip ID','Legs','Slip number','Saved CT','Frozen slip probability','Status','Hits','Misses','Voids','Pending','100% hit','Type','Ranking complete']]
    slip_legs=[['Week','Slip ID','Legs','Slip number','Leg','Sport','Player','Prop','Rule','Threshold','Frozen probability','Actual','Result','Game time CT','Probability status']]
    saved=data.get('weeklyTracking',{}).get('slips',[])
    for w in sorted({s['week'] for s in saved},reverse=True):
        for size in (2,3,4,5,6,8):
            for s in sorted((s for s in saved if s['week']==w and s['size']==size),key=lambda s:s['slot']):
                weekly.append([s['week'],s['id'],s['size'],s['slot'],local_time(s['capturedAt']),s['probability'],s['status'],s['hits'],s['misses'],s['voids'],s['pending'],s['allHit'],'Model test only',s.get('searchComplete')])
                for i,r in enumerate(s['legs'],1):
                    slip_legs.append([s['week'],s['id'],s['size'],s['slot'],i,r.get('sport'),r.get('player'),r.get('prop'),'>' if r.get('usesModelLine') else '>=',r['modelLine'] if r.get('usesModelLine') else r['target'],r['probability'],r.get('actual'),r['status'],local_time(r['startTime']),r.get('probabilityStatus')])
    return {'status':status,'forecasts':forecasts,'matched_lines':offers,'slips':slips,'results':results,'model_performance':performance,'weekly_slips':weekly,'slip_legs':slip_legs}

def export(root=ROOT):
    data=json.loads((root/'data.json').read_text());ledger=json.loads((root/'ledger.json').read_text())
    out=root/'sheets';out.mkdir(exist_ok=True)
    result=tables(data,ledger)
    for name,rows in result.items():
        buffer=io.StringIO(newline='');writer=csv.writer(buffer,lineterminator='\n');writer.writerows([[cell(v) for v in row] for row in rows])
        text=buffer.getvalue()
        if len(text.encode('utf-8'))>1800000:raise ValueError('Sheet export exceeds safe import size: '+name)
        tmp=out/(name+'.tmp');tmp.write_text(text);tmp.replace(out/(name+'.csv'))
    return result

if __name__=='__main__':export()
