"""Automatic conservative eligibility from prospective, observed exact-line holdouts only."""
from collections import defaultdict,Counter
from validation import key,pregame,graded,holdout,support,finite,iso,score
from line_pipeline import observed_valid

MAX_ABS_CALIBRATION_BIAS=.05
POLICY='sleeper-exact-line-holdout-v1'

def report(ledger,now):
    buckets=defaultdict(list);seen=set();invalid=0
    for row in sorted(ledger,key=lambda r:str(r.get('capturedAt',''))):
        if row.get('forecastKind')!='SLEEPER_LINE':continue
        if not pregame(row) or not observed_valid(row):invalid+=1;continue
        if row['id'] in seen:continue
        seen.add(row['id']);buckets[key(row)].append(row)
    groups=[]
    for k,rows in sorted(buckets.items()):
        complete=[r for r in rows if graded(r) and iso(r['gradedAt'])<=now];review=holdout(complete)
        target_reviews=[]
        for target in review['targetReviews']:
            bias=target['forecastScores']['calibrationBias']
            approved=(review['status']=='REVIEWABLE_HOLDOUT' and review.get('beatsReference') is True and
                      target.get('beatsReference') is True and finite(bias) and abs(bias)<=MAX_ABS_CALIBRATION_BIAS and
                      abs(review['forecastScores']['calibrationBias'])<=MAX_ABS_CALIBRATION_BIAS)
            target_reviews.append(dict(target,eligible=approved,status='VALIDATED_LINE' if approved else target['status']))
        groups.append(dict(sport=k[0],prop=k[1],direction=k[2],sourceVersion=k[3],calibrationVersion=k[4],
            recorded=support(rows),graded=support(complete),scores=score(complete),pending=sum(r.get('resultStatus')=='PENDING' for r in rows),
            void=sum(r.get('resultStatus')=='VOID' for r in rows),review=review,targets=target_reviews,
            eligibleTargets=sum(t['eligible'] for t in target_reviews)))
    totals={sport:dict(recorded=sum(g['recorded']['forecasts'] for g in groups if g['sport']==sport),
                      graded=sum(g['graded']['forecasts'] for g in groups if g['sport']==sport),
                      pending=sum(g['pending'] for g in groups if g['sport']==sport),
                      eligibleTargets=sum(g['eligibleTargets'] for g in groups if g['sport']==sport)) for sport in ('MLB','NFL','NBA','NHL')}
    return dict(policy=POLICY,evaluatedAt=now.isoformat(),groups=groups,sports=totals,invalidObservations=invalid,
                maxAbsCalibrationBias=MAX_ABS_CALIBRATION_BIAS,
                method='Only frozen fresh observed Sleeper thresholds; source/calibration versions separate; later whole-game holdout; existing validation minimums; exact threshold must beat training-only reference on Brier and log loss and pass calibration bias.')

def apply(rows,evidence,now):
    approved={}
    for g in evidence['groups']:
        k=(g['sport'],g['prop'],g['direction'],g['sourceVersion'],g['calibrationVersion'])
        for t in g['targets']:
            if t['eligible']:approved[(k,t['modelLine'])]=t
    promoted=0
    for r in rows:
        if r.get('forecastKind')!='SLEEPER_LINE':continue
        # Revoke automatically when the current evidence no longer passes.
        r.update(platformEligible=False,probabilityStatus='UNVALIDATED_BASELINE',actionable=False,platform=None,platformLine=None)
        t=approved.get((key(r),r.get('modelLine')))
        if t and observed_valid(r,now):
            r.update(platformEligible=True,probabilityStatus='PROSPECTIVELY_VALIDATED_LINE',
                     validationPolicy=POLICY,validationHoldoutPlayerGames=t['holdout']['playerGames'])
            promoted+=1
    return promoted
