"""NFL model-target adapter. Exact platform offers are handled separately.
Kickoffs use nflverse's Eastern-time schedule, never the device timezone.
"""
import csv, io, json, math, urllib.request
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from collections import Counter

FEED = 'https://script.google.com/macros/s/AKfycbyU6Gb-uE-dpVIPwYMKhlp6KITzz3mx_HRfQvdt1rlo1JAAO-y4b_UOv01B48bCjy5O/exec?action=mobileData'
SCHEDULE = 'https://raw.githubusercontent.com/nflverse/nfldata/master/data/games.csv'
STATS = 'https://github.com/nflverse/nflverse-data/releases/download/stats_player/stats_player_week_{season}.csv'
METRICS = {'Pass Yards':'passing_yards','Pass Attempts':'attempts','Pass Completions':'completions','Pass TDs':'passing_tds','Interceptions':'passing_interceptions','Rush Yards':'rushing_yards','Rush Attempts':'carries','Receiving Yards':'receiving_yards','Receptions':'receptions','Targets':'targets','Fantasy Points PPR':'fantasy_points_ppr'}

def num(v):
    if v is None or v == '' or isinstance(v,bool): return None
    try:
        n=float(v)
        return n if math.isfinite(n) else None
    except (ValueError,TypeError): return None

def team(s): return {'JAC':'JAX','LA':'LAR'}.get(s,s)
def instant(v): return datetime.fromisoformat(v.replace('Z','+00:00'))
def kickoff(g):
    return datetime.strptime(g['gameday']+' '+g['gametime'],'%Y-%m-%d %H:%M').replace(tzinfo=ZoneInfo('America/New_York')).astimezone(timezone.utc)

def cache_read(root,name,url,max_age,json_data=False):
    path=Path(root)/'.runtime'/name
    path.parent.mkdir(exist_ok=True)
    if path.exists() and datetime.now(timezone.utc).timestamp()-path.stat().st_mtime < max_age:
        raw=path.read_text()
    else:
        req=urllib.request.Request(url,headers={'User-Agent':'MultiSport-Pickem/0.3'})
        with urllib.request.urlopen(req,timeout=30) as response: raw=response.read().decode('utf-8-sig')
        # A malformed feed never overwrites a good cache.
        json.loads(raw) if json_data else list(csv.DictReader(io.StringIO(raw)))
        tmp=path.with_suffix('.tmp');tmp.write_text(raw);tmp.replace(path)
    return json.loads(raw) if json_data else list(csv.DictReader(io.StringIO(raw)))

def collect(now,get_json,model,corrected,root,norm):
    source_cache=Path(root)/'.runtime'/'nfl-model.json'
    cached=False
    try:
        feed=get_json(FEED)
    except Exception:
        if not source_cache.exists():raise
        feed=json.loads(source_cache.read_text());cached=True
    if feed.get('error') or not isinstance(feed.get('picks'),list):raise ValueError('NFL model unavailable')
    age=(now-instant(feed['generatedAt'])).total_seconds()
    refreshed=datetime.strptime(feed['lastRefresh'],'%m/%d/%Y %H:%M:%S').replace(tzinfo=ZoneInfo('America/Chicago'))
    if not(-300<=age<=3600 and -300<=(now-refreshed).total_seconds()<=86400):
        return [],{'status':'STALE','sourceStatus':'STALE','verifiedRows':0},Counter(stale_source=len(feed['picks']))
    if not cached:
        source_cache.parent.mkdir(exist_ok=True)
        tmp=source_cache.with_suffix('.tmp');tmp.write_text(json.dumps(feed));tmp.replace(source_cache)
    season,week=int(feed['season']),int(feed['week'])
    schedule=cache_read(root,'nfl-schedule.csv',SCHEDULE,3600)
    games=[g for g in schedule if num(g.get('season'))==season and num(g.get('week'))==week and g.get('game_type')=='REG']
    projections={(norm(p['Player']),team(p['Team'])):p for p in feed.get('projections',[]) if p.get('Player') and p.get('Team')}
    rejected=Counter();out=[];roster=None
    for row in feed['picks']:
        public_board=row.get('Line Source')=='Public Sleeper board'
        if row.get('Line Source')!='Automatic model target' and not public_board:
            rejected['nonautomatic_line']+=1;continue
        if public_board:
            board=feed.get('boardStatus',{})
            try:board_age=(now-instant(board['fetchedAt'])).total_seconds()
            except (KeyError,ValueError,TypeError,AttributeError):board_age=None
            if (row.get('Platform')!='Sleeper' or not row.get('Board ID') or
                board.get('status')!='ok' or board.get('sources',{}).get('Sleeper',{}).get('status')!='ok' or
                board_age is None or not -300<=board_age<=900):
                rejected['unverified_public_board']+=1;continue
        matches=[g for g in games if {team(g['home_team']),team(g['away_team'])}=={team(row.get('Team')),team(row.get('Opponent'))}]
        if len(matches)!=1:rejected['unverified_game']+=1;continue
        g=matches[0]
        try: start=kickoff(g)
        except (KeyError,ValueError):rejected['missing_kickoff']+=1;continue
        if start<=now or g.get('home_score') not in ('',None) or g.get('away_score') not in ('',None):
            rejected['game_started']+=1;continue
        if row.get('Model Side')!='Higher':rejected['unsupported_direction']+=1;continue
        p,line,samples,snaps=[num(row.get(k)) for k in ('Probability','Line','History Sample','Expected Snap %')]
        if p is None or not 0<p<1 or line is None or samples is None or samples<4 or snaps is None or not 0<snaps<=1:
            rejected['missing_probability_or_usage']+=1;continue
        if public_board and (line<.5 or abs(line-(math.floor(line)+.5))>1e-9):
            rejected['unsupported_public_threshold']+=1;continue
        if any(s in str(row.get('Availability','')).upper() for s in ('OUT','INACTIVE','DOUBTFUL','SUSPEND','PUP','IR')):
            rejected['unavailable_player']+=1;continue
        pr=projections.get((norm(row.get('Player')),team(row.get('Team'))))
        if not pr or num(pr.get('Week'))!=week or not pr.get('Player ID'):
            rejected['projection_week_or_identity']+=1;continue
        if roster is None:roster=cache_read(root,'nfl-roster.json','https://api.sleeper.app/v1/players/nfl',86400,True)
        identity=[x for x in roster.values() if x.get('gsis_id')==pr['Player ID'] and team(x.get('team'))==team(row['Team']) and norm(x.get('full_name'))==norm(row['Player']) and x.get('active') is True and str(x.get('injury_status','')).upper() not in ('OUT','IR','PUP','DOUBTFUL','SUSPENDED')]
        if len(identity)!=1:rejected['player_team_mismatch']+=1;continue
        if row['Market'] not in METRICS and row['Market']!='Rush + Receiving Yards':rejected['unsupported_stat']+=1;continue
        r={'id':f"NFL:{g['game_id']}:{pr['Player ID']}:{row['Market']}:MORE:{line}", 'sport':'NFL', 'gameId':g['game_id'],'playerId':pr['Player ID'],'player':row['Player'],'team':team(row['Team']),'opponent':team(row['Opponent']),'prop':row['Market'],'direction':'MORE','target':line+.5,'modelLine':line,'projection':num(row.get('Model Projection')),'sourceProbability':p,'samples':samples,'startTime':start.isoformat(),'officialGameDate':g['gameday'],'scheduleVerified':True,'homeTeamAbbr':team(g['home_team']),'awayTeamAbbr':team(g['away_team']),'capturedAt':now.isoformat(),'lineupStatus':f'{snaps:.0%} expected snaps','expectedPlayingTime':snaps,'probabilityStatus':'UPSTREAM SHRUNK HISTORY ESTIMATE','platformLine':None,'platform':None,'actionable':False,'resultStatus':'PENDING','season':season,'week':week,'upstreamModelVersion':feed.get('appVersion')}
        if public_board:
            # New source semantics get separate immutable identities and validation.
            # Upstream board metadata is not a verified offer from this app's provider.
            r.update(id='NFL_PUBLIC_BOARD:'+r['id'],baselineVersion='nfl-public-board-upstream-v1',
                     probabilityStatus='UNVALIDATED_BASELINE',platformEligible=False,
                     upstreamBoardId=str(row['Board ID']),upstreamBoardObservedAt=board['fetchedAt'])
        r['probability']=corrected(r,model);r['modelVersion']=model['version'];out.append(r)
    public_board_rows=sum(r.get('baselineVersion')=='nfl-public-board-upstream-v1' for r in out)
    model_target_rows=len(out)-public_board_rows
    status='LIVE_FORECASTS' if model_target_rows else 'BASELINE_FORECASTS' if public_board_rows else 'LIVE_FORECASTS'
    return out,{'status':status,'sourceStatus':'CURRENT','verifiedRows':len(out),
                'automaticModelTargetRows':model_target_rows,'publicBoardBaselineRows':public_board_rows,
                'modelVersion':feed.get('appVersion'),'sourceUpdatedAt':feed['generatedAt'],
                'sourceRefresh':feed['lastRefresh'],'week':week,'season':season,'usingCachedFeed':cached},rejected

def grade(ledger, now, root):
    pending = [r for r in ledger if r['sport'] == 'NFL' and r.get('resultStatus') == 'PENDING' and instant(r['startTime']) <= now]
    game_ids = list(dict.fromkeys(r['gameId'] for r in pending))
    checked = len(game_ids)
    if not pending:
        return {'gradingStatus': 'CURRENT', 'gradingGamesChecked': 0, 'gradingGamesUnavailable': 0}

    try:
        schedule_rows = cache_read(root, 'nfl-schedule.csv', SCHEDULE, 3600)
        schedule = {g['game_id']: g for g in schedule_rows if g.get('game_id')}
    except Exception:
        return {'gradingStatus': 'AWAITING_RESULT_SOURCE',
                'gradingGamesChecked': checked, 'gradingGamesUnavailable': checked}

    missing_schedule = {gid for gid in game_ids if gid not in schedule}
    final_rows = []
    for r in pending:
        game = schedule.get(r['gameId'])
        if game and num(game.get('home_score')) is not None and num(game.get('away_score')) is not None:
            final_rows.append(r)

    stats = {}
    failed_seasons = set()
    for season in sorted({r['season'] for r in final_rows}):
        try:
            rows = cache_read(root, f'nfl-stats-{season}.csv', STATS.format(season=season), 3600)
            indexed = {}
            for row in rows:
                week = num(row.get('week'))
                if week is None or int(week) != week:
                    continue
                indexed[(row.get('player_id'), int(week), row.get('season_type'))] = row
            stats[season] = indexed
        except Exception:
            failed_seasons.add(season)

    unavailable_games = set(missing_schedule)
    unavailable_games.update(r['gameId'] for r in final_rows if r['season'] in failed_seasons)

    for r in pending:
        game = schedule.get(r['gameId'])
        if not game or num(game.get('home_score')) is None or num(game.get('away_score')) is None:
            continue
        if r['season'] in failed_seasons:
            continue
        row = stats.get(r['season'], {}).get((r['playerId'], r['week'], 'REG'))
        if not row or team(row.get('team') or row.get('recent_team')) != r['team'] or team(row.get('opponent_team')) != r['opponent']:
            continue
        if row.get('game_id') and row['game_id'] != r['gameId']:
            continue
        if r['prop'] == 'Rush + Receiving Yards':
            values = [num(row.get(k)) for k in ('rushing_yards', 'receiving_yards')]
            value = sum(values) if all(v is not None for v in values) else None
        else:
            value = num(row.get(METRICS.get(r['prop'], '')))
        if value is None:
            continue
        r.update(resultStatus='GRADED', actual=value, outcome=int(value > r['modelLine']), gradedAt=now.isoformat())

    unavailable = len(unavailable_games)
    status = 'CURRENT' if unavailable == 0 else 'AWAITING_RESULT_SOURCE' if unavailable >= checked else 'PARTIAL_RESULT_SOURCE'
    return {'gradingStatus': status, 'gradingGamesChecked': checked,
            'gradingGamesUnavailable': unavailable}
