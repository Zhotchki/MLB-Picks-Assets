"""Exact-line holdout evidence; NBA/NHL results remain review-only for platform eligibility."""
from collections import defaultdict,Counter
from validation import key,pregame,graded,holdout,support,finite,iso,score
from line_pipeline import observed_valid

MAX_ABS_CALIBRATION_BIAS=.05
POLICY='sleeper-exact-line-holdout-v2'
AUTO_PLATFORM_SPORTS=frozenset(('MLB','NFL'))

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
            platform_allowed=approved and k[0] in AUTO_PLATFORM_SPORTS
            status='VALIDATED_LINE' if platform_allowed else 'VALIDATED_LINE_REVIEW_ONLY' if approved else target['status']
            target_reviews.append(dict(target,eligible=approved,platformEligible=platform_allowed,status=status))
        evidence_count=sum(t['eligible'] for t in target_reviews)
        platform_count=sum(t['platformEligible'] for t in target_reviews)
        groups.append(dict(sport=k[0],prop=k[1],direction=k[2],sourceVersion=k[3],calibrationVersion=k[4],
            recorded=support(rows),graded=support(complete),scores=score(complete),pending=sum(r.get('resultStatus')=='PENDING' for r in rows),
            void=sum(r.get('resultStatus')=='VOID' for r in rows),review=review,targets=target_reviews,
            eligibleTargets=evidence_count,evidenceQualifiedTargets=evidence_count,
            platformEligibleTargets=platform_count,
            platformPromotionPolicy='AUTO_EXACT_LINE' if k[0] in AUTO_PLATFORM_SPORTS else 'REVIEW_ONLY'))
    totals={sport:dict(recorded=sum(g['recorded']['forecasts'] for g in groups if g['sport']==sport),
                      graded=sum(g['graded']['forecasts'] for g in groups if g['sport']==sport),
                      pending=sum(g['pending'] for g in groups if g['sport']==sport),
                      eligibleTargets=sum(g['eligibleTargets'] for g in groups if g['sport']==sport),
                      evidenceQualifiedTargets=sum(g['evidenceQualifiedTargets'] for g in groups if g['sport']==sport),
                      platformEligibleTargets=sum(g['platformEligibleTargets'] for g in groups if g['sport']==sport),
                      platformPromotionPolicy='AUTO_EXACT_LINE' if sport in AUTO_PLATFORM_SPORTS else 'REVIEW_ONLY') for sport in ('MLB','NFL','NBA','NHL')}
    return dict(policy=POLICY,evaluatedAt=now.isoformat(),groups=groups,sports=totals,invalidObservations=invalid,
                maxAbsCalibrationBias=MAX_ABS_CALIBRATION_BIAS,
                method='Frozen fresh observed Sleeper thresholds; separate source/calibration versions; later whole-game holdout; exact thresholds must beat training-only references on Brier and log loss and pass calibration bias. NBA/NHL results are review evidence only and never auto-enable platform offers.')

def apply(rows,evidence,now):
    approved={}
    for g in evidence['groups']:
        k=(g['sport'],g['prop'],g['direction'],g['sourceVersion'],g['calibrationVersion'])
        for t in g['targets']:
            if t.get('platformEligible') is True:approved[(k,t['modelLine'])]=t
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
