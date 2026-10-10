"""Prospective NFL exact-line empirical baseline; never enables platform slips."""
import math
from datetime import timedelta
from collections import Counter
from nfl_adapter import cache_read, SCHEDULE, STATS, METRICS, num, team, kickoff
from platform_feed import match

VERSION = 'nfl-exact-line-empirical-v1'

def collect(forecasts, board, now, root, norm):
    # Use only fresh lines and already verified eligible player/prop identities.
    entry = board.get('sports', {}).get('NFL', {})
    elapsed = now.timestamp() - entry.get('fetchedAtEpoch', 0)
    if not 0 <= elapsed <= 900 or not entry.get('rows'): return [], Counter()
    templates = {}
    for r in forecasts:
        if r.get('sport') == 'NFL' and r.get('platformEligible') is not False and r.get('scheduleVerified'):
            templates.setdefault((str(r['playerId']), str(r['gameId']), r['prop']), r)
    resolved = {}
    for line in entry['rows']:
        value = num(line.get('line'))
        # Whole-number lines can push; fractional PPR scores need a different model.
        if value is None or abs(value - (math.floor(value) + .5)) > 1e-9: continue
        trial = [dict(r, modelLine=value, target=value+.5) for r in templates.values()
                 if r['prop'] != 'Fantasy Points PPR']
        offers, _ = match(trial, dict(board, sports={'NFL':dict(entry, rows=[line])}), now, norm)
        for r in offers:
            original = templates[(str(r['playerId']), str(r['gameId']), r['prop'])]
            if abs(original['modelLine']-value) <= 1e-9: continue
            resolved[(str(r['playerId']), str(r['gameId']), r['prop'], value)] = r
    if not resolved: return [], Counter()
    rejected = Counter()
    try:
        schedule = cache_read(root, 'nfl-schedule.csv', SCHEDULE, 3600)
        games = {}
        for g in schedule:
            if g.get('game_type') != 'REG' or num(g.get('home_score')) is None or num(g.get('away_score')) is None: continue
            try: start = kickoff(g)
            except (KeyError, ValueError): continue
            if now-timedelta(days=400) <= start <= now-timedelta(hours=4):
                games[(int(g['season']),int(g['week']),team(g['home_team']))] = (g,start)
                games[(int(g['season']),int(g['week']),team(g['away_team']))] = (g,start)
        seasons = sorted({int(r['season']) for r in resolved.values()} | {int(r['season'])-1 for r in resolved.values()})
        stats = []
        for season in seasons:
            stats.extend(cache_read(root, f'nfl-stats-{season}.csv', STATS.format(season=season), 3600))
    except Exception:
        return [], Counter(history_source_unavailable=len(resolved))
    out = []
    for r in resolved.values():
        history = {}
        for s in stats:
            if s.get('player_id') != r['playerId'] or s.get('season_type') != 'REG' or team(s.get('team') or s.get('recent_team')) != r['team']: continue
            try: event = games.get((int(s['season']),int(s['week']),r['team']))
            except (KeyError, ValueError, TypeError): continue
            if not event: continue
            g,start = event
            if s.get('game_id') and s['game_id'] != g['game_id']: continue
            opponent = team(g['away_team'] if team(g['home_team']) == r['team'] else g['home_team'])
            if team(s.get('opponent_team')) != opponent: continue
            if r['prop'] == 'Rush + Receiving Yards':
                vals = [num(s.get(k)) for k in ('rushing_yards','receiving_yards')]
                value = sum(vals) if all(v is not None for v in vals) else None
            else: value = num(s.get(METRICS.get(r['prop'],'')))
            if value is None: continue
            history[g['game_id']] = (start,value)
        observations = sorted(history.values(), reverse=True)[:25]
        if len(observations) < 8 or not observations or observations[0][0] < now-timedelta(days=21):
            rejected['insufficient_recent_history'] += 1; continue
        values = [v for _,v in observations]
        probability = (sum(v > r['modelLine'] for v in values)+1)/(len(values)+2)
        candidate = dict(r, id=f"NFL:{r['gameId']}:{r['playerId']}:{r['prop']}:MORE:{r['modelLine']}:{VERSION}",
                         probability=probability, sourceProbability=probability, samples=len(values),
                         projection=sum(values)/len(values), baselineVersion=VERSION,
                         probabilityStatus='UNVALIDATED_BASELINE', platformEligible=False,
                         actionable=False, platform=None, platformLine=None, resultStatus='PENDING',
                         capturedAt=now.isoformat(), calibrationOffset=0,
                         modelVersion=VERSION, upstreamModelVersion=VERSION,
                         observedPlatformLine=r['modelLine'],
                         baselineNote='Smoothed same-team historical exceedance; no matchup or playing-time adjustment.')
        for key in ('offerId','provider','offerObservedAt','platformEventId','requiresPlatformReview','platformOfferType','kickoffSource','payoutMultiplier'):
            candidate.pop(key,None)
        out.append(candidate)
    return out,rejected
