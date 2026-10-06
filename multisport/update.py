"""Automatic v0.3.1 MLB/NFL adapter, immutable forecasts, final grading and weekly validation.
Uses only stdlib. Platform lines are NOT inferred from model thresholds.
"""
import json, math, unicodedata, urllib.request, urllib.parse, os
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent
VERSION = '0.5.1'
API = 'https://statsapi.mlb.com/api/v1/'
STAT_KEYS = {'Hits': 'hits', 'Runs': 'runs', 'RBI': 'rbi', 'Bases': 'totalBases', 'Walks': 'baseOnBalls', 'Strikeouts': 'strikeOuts', 'Stolen Bases': 'stolenBases', 'Home Runs': 'homeRuns'}

def get(url,timeout=40):
    req = urllib.request.Request(url, headers={'User-Agent': 'MultiSport-Pickem/0.3'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)

def read(name, default):
    p = ROOT / name
    return json.loads(p.read_text()) if p.exists() else default

def write(name, data):
    p = ROOT / name
    tmp = p.with_suffix(p.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')))
    tmp.replace(p)

def norm(s):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(s)).casefold() if c.isalnum())

def number(v):
    if v is None or v == '' or isinstance(v, bool): return None
    try:
        v = float(v)
        return v if math.isfinite(v) else None
    except (TypeError, ValueError): return None

def iso(v):
    return datetime.fromisoformat(v.replace('Z', '+00:00'))

def prob(row):
    v = row.get('Adjusted Probability')
    if v is None or v == '': v = row.get('Probability')
    p = number(v)
    return p if p is not None and 0 < p < 1 else None

def actual(prop, stats):
    if prop == 'Hits + Runs + RBI':
        values = [number(stats.get(k)) for k in ('hits', 'runs', 'rbi')]
        return sum(values) if all(v is not None for v in values) else None
    return number(stats.get(STAT_KEYS.get(prop, '')))

def group(row):
    key = row['sport'] + '|' + row['prop'] + '|' + row['direction']
    version = row.get('baselineVersion') or row.get('upstreamModelVersion')
    return key + '|' + str(version) if version else key
def corrected(row, model):
    p = row['sourceProbability'] + model.get('offsets', {}).get(group(row), 0)
    return max(.01, min(.99, p))

def metrics(rows, model):
    if not rows: return {'n': 0, 'brier': None, 'logLoss': None}
    from validation import score,player_game,event
    scores = score(rows,lambda r:corrected(r,model))
    return {'n':len(rows),'playerGames':len({player_game(r) for r in rows}),'games':len({event(r) for r in rows}),
            'brier':scores['brier'],'logLoss':scores['logLoss']}

def learn(ledger, incumbent, today):
    week = today.strftime('%G-W%V')
    if today.weekday() != 0 or incumbent.get('lastReviewWeek') == week: return incumbent
    # Split by entire games so multiple props for one game never cross train/test.
    from validation import pregame,graded,player_game,event
    rows=[];seen=set()
    for r in sorted(ledger,key=lambda r:str(r.get('capturedAt',''))):
        if not pregame(r) or not graded(r) or r['id'] in seen:continue
        seen.add(r['id'])
        source_p=number(r.get('sourceProbability'))
        if source_p is not None and 0<source_p<1:rows.append(dict(r,sourceProbability=source_p))
    games = sorted({(iso(r['startTime']),event(r)) for r in rows})
    cut = int(len(games)*.8)
    train_games = {g for _,g in games[:cut]}
    train = [r for r in rows if event(r) in train_games]
    test = [r for r in rows if event(r) not in train_games]
    updated = dict(incumbent, lastReviewWeek=week)
    training_players=len({player_game(r) for r in train});holdout_players=len({player_game(r) for r in test})
    if training_players < 200 or holdout_players < 50 or len(games) < 10:
        updated['review'] = {'status':'COLLECTING_RESULTS','trainingRows':len(train),'holdoutRows':len(test),
                             'trainingPlayerGames':training_players,'holdoutPlayerGames':holdout_players,'games':len(games)}
        return updated
    buckets = defaultdict(list)
    for r in train: buckets[group(r)].append(r)
    # Test data newer than the incumbent's training data; reuse cannot justify promotion.
    fresh = not incumbent.get('trainedThrough') or min(iso(r['startTime']) for r in test) > iso(incumbent['trainedThrough'])
    candidate={'version':'weekly-'+week,'offsets':dict(incumbent.get('offsets',{}))}
    reviews={};accepted=[]
    for k,rs in buckets.items():
        later=[r for r in test if group(r)==k]
        players=defaultdict(list)
        for r in rs:players[player_game(r)].append(r['outcome']-r['sourceProbability'])
        n=len(players);later_n=len({player_game(r) for r in later})
        detail={'trainingPlayerGames':n,'holdoutPlayerGames':later_n,'trainingGames':len({event(r) for r in rs}),'holdoutGames':len({event(r) for r in later})}
        if n<50 or later_n<25 or detail['trainingGames']<10 or detail['holdoutGames']<5:
            reviews[k]=dict(detail,status='COLLECTING_SEPARATE_GAMES');continue
        offset=sum(sum(v)/len(v) for v in players.values())/(n+50)
        proposed={'offsets':dict(incumbent.get('offsets',{}),**{k:offset})}
        base_group,trial_group=metrics(later,incumbent),metrics(later,proposed)
        passes=fresh and trial_group['brier']<base_group['brier']-.001 and trial_group['logLoss']<base_group['logLoss']-.001
        reviews[k]=dict(detail,status='PASSED' if passes else 'KEPT_CURRENT_GROUP',baseline=base_group,candidate=trial_group)
        if passes:candidate['offsets'][k]=offset;accepted.append(k)
    base, trial = metrics(test, incumbent), metrics(test, candidate)
    promote = fresh and bool(accepted) and trial['brier'] < base['brier']-.001 and trial['logLoss'] < base['logLoss']-.001
    if promote:
        updated.update(candidate, trainedThrough=max(train,key=lambda r:iso(r['startTime']))['startTime'])
    updated['review'] = {'status':'PROMOTED' if promote else 'KEPT_CURRENT_MODEL','trainingRows':len(train),'holdoutRows':len(test),
                        'trainingPlayerGames':training_players,'holdoutPlayerGames':holdout_players,'baseline':base,'candidate':trial,
                        'freshHoldout':fresh,'groupReviews':reviews,'acceptedGroups':accepted if promote else []}
    return updated

def collect_mlb(now, today, model):
    upstream = get('https://script.google.com/macros/s/AKfycbw1_xLZM-fAaBm9c4hmvwrvdlWxbV-3S3gW3e8GCZ8DKsfpNf-FVlwHb4lhwMECXNoiAA/exec?api=mobile')
    timestamp = upstream.get('generatedAt')
    try:
        age = (now-iso(timestamp)).total_seconds()
        source_fresh = -300 <= age <= 3600
    except (ValueError, TypeError, AttributeError):
        source_fresh = False
    # Use underlying refresh time too, because copying an old snapshot does not refresh forecasts.
    refresh = upstream.get('lastRefresh')
    if refresh:
        try:
            refreshed = datetime.strptime(refresh, '%m/%d/%Y %I:%M:%S %p').replace(tzinfo=ZoneInfo('America/Chicago'))
            source_fresh = source_fresh and -300 <= (now-refreshed).total_seconds() <= 7200
        except ValueError:
            source_fresh = False
    else:
        source_fresh = False
    schedule = get(API + 'schedule?' + urllib.parse.urlencode({'sportId':1,'date':today.isoformat()}))
    games = [g for d in schedule.get('dates',[]) for g in d.get('games',[])]
    team_info = {t['id']:t for t in get(API+'teams?sportId=1')['teams']}
    boxes = {}
    def box(game_id):
        if game_id not in boxes: boxes[game_id] = get(API+f'game/{game_id}/boxscore')
        return boxes[game_id]
    verified = []
    rejected = Counter()
    if not source_fresh: rejected['stale_source'] = len(upstream.get('picks',[]))
    for row in (upstream.get('picks',[]) if source_fresh else []):
        p, target = prob(row), number(row.get('Probability Threshold'))
        if p is None or target is None or target < 0:
            rejected['missing_probability_or_target'] += 1; continue
        if number(row.get('Probability Samples')) is None or float(row['Probability Samples']) < 25:
            rejected['insufficient_support'] += 1; continue
        if row.get('Prop') not in STAT_KEYS and row.get('Prop') != 'Hits + Runs + RBI':
            rejected['unsupported_stat'] += 1; continue
        if str(row.get('Direction','')).upper() != 'MORE':
            rejected['unsupported_threshold_direction'] += 1; continue
        if any(s in str(row.get('Injury Status','')).upper() for s in ('INJURED','OUT','SUSPENDED','IL')):
            rejected['unavailable_player'] += 1; continue
        matches = []
        for g in games:
            home, away = (g['teams'][s]['team']['id'] for s in ('home','away'))
            abbrevs = {team_info[home]['abbreviation'],team_info[away]['abbreviation']}
            if {row.get('Team'),row.get('Opponent')} == abbrevs:
                matches.append(g)
        if len(matches)!=1:
            rejected['unverified_or_ambiguous_game'] += 1; continue
        g = matches[0]
        if g['status']['abstractGameState'] != 'Preview' or iso(g['gameDate']) <= now:
            rejected['game_started'] += 1; continue
        side = next(s for s in ('home','away') if team_info[g['teams'][s]['team']['id']]['abbreviation']==row['Team'])
        players = box(g['gamePk'])['teams'][side]['players']
        identity = [v for v in players.values() if norm(v['person']['fullName']) == norm(row['Player'])]
        if len(identity)!=1:
            rejected['player_team_mismatch'] += 1; continue
        player = identity[0]
        r = {'id':f"MLB:{g['gamePk']}:{player['person']['id']}:{row['Prop']}:MORE:{target}",
             'sport':'MLB','gameId':g['gamePk'],'playerId':player['person']['id'],'player':player['person']['fullName'],
             'team':row['Team'],'opponent':row['Opponent'],'homeTeam':team_info[g['teams']['home']['team']['id']]['name'],'awayTeam':team_info[g['teams']['away']['team']['id']]['name'],'prop':row['Prop'],'direction':'MORE',
             'target':target,'projection':number(row.get('Model Projection')), 'sourceProbability':p,
             'samples':row['Probability Samples'],'startTime':g['gameDate'],'officialGameDate':g.get('officialDate',today.isoformat()),'scheduleVerified':True, 'capturedAt':now.isoformat(),
             'lineupStatus':row.get('Lineup Status'), 'probabilityStatus':row.get('Probability Status'),
             'platformLine':None,'platform':None,'actionable':False, 'resultStatus':'PENDING'}
        r['probability'] = corrected(r, model)
        r['modelVersion'] = model['version']
        r['upstreamModelVersion'] = upstream.get('appVersion') or upstream.get('version')
        verified.append(r)
    return verified, {'status':'LIVE_FORECASTS' if source_fresh else 'STALE','sourceStatus':'CURRENT' if source_fresh else 'STALE','verifiedRows':len(verified)}, rejected, timestamp, refresh

def grade_mlb(ledger, now):
    boxes = {}
    def box(game_id):
        if game_id not in boxes: boxes[game_id] = get(API+f'game/{game_id}/boxscore')
        return boxes[game_id]
    event_cache = {}
    for r in ledger:
        if r['sport'] != 'MLB' or r.get('resultStatus') != 'PENDING' or iso(r['startTime']) > now: continue
        if r['gameId'] not in event_cache:
            event_cache[r['gameId']] = get(API+'schedule?'+urllib.parse.urlencode({'sportId':1,'gamePk':r['gameId']}))
        dates = event_cache[r['gameId']]
        events = [g for d in dates.get('dates',[]) for g in d.get('games',[])]
        if not events: continue
        event = next((g for g in events if g['gamePk']==r['gameId']),None)
        if not event: continue
        status = event['status']
        if status.get('codedGameState') in ('C','D'):
            r.update(resultStatus='VOID', voidReason='Cancelled or postponed'); continue
        if status['abstractGameState'] != 'Final': continue
        found = [p for s in box(r['gameId'])['teams'].values() for p in s['players'].values() if p['person']['id']==r['playerId']]
        stats = found[0].get('stats',{}).get('batting',{}) if found else {}
        if number(stats.get('plateAppearances')) in (None,0):
            r.update(resultStatus='VOID', voidReason='No plate appearance'); continue
        val = actual(r['prop'],stats)
        if val is None: continue
        r.update(resultStatus='GRADED', actual=val, outcome=int(val>=r['target']), gradedAt=now.isoformat())

def run():
    now = datetime.now(timezone.utc)
    today = now.astimezone(ZoneInfo('America/Chicago')).date()
    ledger = read('ledger.json', [])
    model = read('model.json', {'version':'upstream-baseline', 'offsets':{}})
    verified = []
    rejected = Counter()
    timestamp = refresh = None
    mlb_status = {'status':'UNAVAILABLE','sourceStatus':'UNAVAILABLE','verifiedRows':0}
    try:
        mlb_rows,mlb_status,mlb_rejected,timestamp,refresh = collect_mlb(now,today,model)
        verified.extend(mlb_rows)
        rejected.update(mlb_rejected)
    except Exception:
        mlb_status['detail'] = 'MLB feed could not be verified this run; other sports continue.'
        rejected['MLB:unavailable_source'] += 1
    from nfl_adapter import collect as collect_nfl, grade as grade_nfl
    nfl_status = {'status':'UNAVAILABLE','sourceStatus':'UNAVAILABLE','verifiedRows':0}
    try:
        nfl_rows,nfl_status,nfl_rejected = collect_nfl(now,lambda url:get(url,timeout=90),model,corrected,ROOT,norm)
        verified.extend(nfl_rows)
        rejected.update({'NFL:'+k:v for k,v in nfl_rejected.items()})
    except Exception as error:
        nfl_status['detail'] = 'NFL feed could not be verified this run; MLB continues.'
        rejected['NFL:unavailable_source'] += 1
    from nhl_adapter import collect as collect_nhl, grade as grade_nhl
    nhl_status = {'status':'UNAVAILABLE','sourceStatus':'UNAVAILABLE','verifiedRows':0}
    try:
        nhl_rows,nhl_status,nhl_rejected = collect_nhl(datetime.now(timezone.utc),ROOT,model,corrected,norm)
        verified.extend(nhl_rows)
        rejected.update({'NHL:'+k:v for k,v in nhl_rejected.items()})
    except Exception:
        nhl_status['detail'] = 'NHL sources could not be verified this run; other sports continue.'
        rejected['NHL:unavailable_source'] += 1
    from nba_adapter import collect as collect_nba, grade as grade_nba
    nba_status = {'status':'UNAVAILABLE','sourceStatus':'UNAVAILABLE','verifiedRows':0}
    try:
        nba_rows,nba_status,nba_rejected = collect_nba(datetime.now(timezone.utc),ROOT,model,corrected,norm)
        verified.extend(nba_rows)
        rejected.update({'NBA:'+k:v for k,v in nba_rejected.items()})
    except Exception:
        nba_status['detail'] = 'NBA sources could not be verified this run; other sports continue.'
        rejected['NBA:unavailable_source'] += 1
    # Recheck after network reads: a slow import must never backdate a prediction
    # for a game that started while its sources were being fetched.
    captured_at = datetime.now(timezone.utc)
    active = [r for r in verified if iso(r['startTime']) > captured_at]
    rejected['started_during_refresh'] += len(verified)-len(active)
    verified = active
    from validation import calibration_signature
    for r in verified:
        r['capturedAt'] = captured_at.isoformat()
        r['calibrationOffset'] = model.get('offsets',{}).get(group(r),0)
        r['calibrationGroupVersion'] = calibration_signature(group(r),r['calibrationOffset'])
    for sport,status in (('MLB',mlb_status),('NFL',nfl_status),('NBA',nba_status),('NHL',nhl_status)):
        status['verifiedRows'] = sum(r['sport']==sport for r in verified)
    # Immutable first pregame snapshot; later refreshes never overwrite predictions.
    ids = {r['id'] for r in ledger}
    for r in verified:
        if r['id'] not in ids: ledger.append(dict(r)); ids.add(r['id'])
    try:
        grade_mlb(ledger,now)
    except Exception:
        mlb_status['gradingStatus'] = 'AWAITING_RESULT_SOURCE'
    try:
        grade_nfl(ledger,now,ROOT)
    except Exception:
        nfl_status['gradingStatus'] = 'AWAITING_RESULT_SOURCE'
    try:
        grade_nhl(ledger,now,ROOT)
    except Exception:
        nhl_status['gradingStatus'] = 'AWAITING_RESULT_SOURCE'
    try:
        grade_nba(ledger,now,ROOT)
    except Exception:
        nba_status['gradingStatus'] = 'AWAITING_RESULT_SOURCE'
    model = learn(ledger,model,today)
    from validation import report as validation_report
    validation = validation_report(ledger)
    graded = [r for r in ledger if r.get('resultStatus')=='GRADED']
    frozen = {'n':len(graded), 'brier':sum((r['probability']-r['outcome'])**2 for r in graded)/len(graded) if graded else None}
    from platform_feed import fetch as fetch_board,match as match_offers,slips as build_slips
    published_at = datetime.now(timezone.utc)
    board,feed_state=fetch_board(ROOT,published_at)
    offers,offer_counts=match_offers(verified,board,published_at,norm)
    data = {'version':VERSION,'updatedAt':published_at.isoformat(),'sourceUpdatedAt':timestamp,'sourceRefresh':refresh,'sourceStatus':mlb_status['sourceStatus'],
            'sports':{'MLB':mlb_status, 'NFL':nfl_status,'NBA':nba_status,'NHL':nhl_status},
            'picks':sorted(verified,key=lambda r:-r['probability']),'rejected':dict(rejected),'model':model,'validation':validation,
            'results':{'recorded':len(ledger),'graded':len(graded),'void':sum(r.get('resultStatus')=='VOID' for r in ledger),'frozenPredictionMetrics':frozen},
            'slipStatus':('REVIEW_REQUIRED' if any(r.get('requiresPlatformReview') for r in offers) else 'READY') if offers else 'WAITING_FOR_VERIFIED_PLATFORM_LINES','platformFeed':{**{k:v for k,v in board.items() if k!='sports'},'sportStatus':{s:{k:v for k,v in entry.items() if k!='rows'} for s,entry in board.get('sports',{}).items()}},'offerCounts':offer_counts,'offers':offers,'slips':{str(size):build_slips(offers,size) for size in (2,3,4,5,6,8)}}
    write('feed-state.json',feed_state); write('ledger.json',ledger); write('model.json',model); write('data.json',data)
    print(json.dumps({'verifiedForecasts':len(verified),'rejected':dict(rejected),'ledger':len(ledger),'graded':len(graded)}))

if __name__ == '__main__': run()
