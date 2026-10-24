function validationEscape(value) {
  return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function validationValue(value, digits = 3) {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—';
}
function validationMarkup(report, sport = 'All sports') {
  if (!report) return '<div class="panel">Validation reports will appear after the automatic feed updates.</div>';
  const esc = validationEscape;
  const statuses = {WAITING_FOR_FORECASTS:'Waiting for eligible forecasts', COLLECTING_RESULTS:'Collecting final results',
    COLLECTING_SEPARATE_GAMES:'Collecting separate training and holdout games',
    INSUFFICIENT_TRAINING_FOR_TARGETS:'More training results needed for these targets', REVIEWABLE_HOLDOUT:'Holdout ready for model review'};
  const groups = (report.groups || []).filter(g => sport === 'All sports' || g.sport === sport);
  if (!groups.length) return '<div class="panel">No saved forecasts for this sport yet.</div>';
  return groups.map(g => {
    const review = g.review, score = g.scores, errors = g.projectionErrors;
    const progress = [['Player-games','playerGames'],['Separate games','games'],['Game dates','days']].map(([label,key]) =>
      '<tr><td>'+label+'</td><td>'+esc(review.training[key])+' / '+esc(review.minimums['training'+key[0].toUpperCase()+key.slice(1)])+'</td><td>'+esc(review.holdout[key])+' / '+esc(review.minimums['holdout'+key[0].toUpperCase()+key.slice(1)])+'</td></tr>').join('');
    const percent = v => v == null ? '—' : validationValue(v*100,1)+'%';
    const skill = review.forecastScores ? '<p>Later holdout Brier: '+validationValue(review.forecastScores.brier)+
      ' · Training-only reference: '+validationValue(review.referenceScores.brier)+
      '<br><small>Better on both Brier and log loss: '+(review.beatsReference?'yes':'no')+'. Exact targets all pass: '+
      (review.allTargetsBeatReference?'yes':'no')+'. This comparison does not enable playable offers.</small></p>' : '';
    const targets = (review.targetReviews || []).length ? '<details><summary>Exact target holdout checks</summary><ul>'+
      review.targetReviews.map(t => '<li>'+esc(t.modelLine == null ? t.target : t.modelLine)+' · '+
        esc(t.holdout.playerGames)+' holdout player-games · '+(t.status==='REVIEWABLE_TARGET'?(t.beatsReference?'beats reference':'does not beat reference'):'collecting support')+'</li>').join('')+
      '</ul><small>Every sufficiently supported target must improve both Brier score and log loss. These checks do not enable playable offers.</small></details>' : '';
    return '<article class="panel"><h2>'+esc(g.sport)+' · '+esc(g.prop)+'</h2><p>'+esc(statuses[g.status] || g.status)+
      '</p><small>'+esc(g.sourceVersion || 'No source forecasts yet')+(g.modelVersion?' · '+esc((g.modelVersions || [g.modelVersion]).join(', ')):'')+'</small><p>'+esc(g.recorded.forecasts)+
      ' saved targets · '+esc(g.recorded.playerGames)+' player-games<br>'+esc(g.graded.playerGames)+' graded player-games · '+esc(g.pending)+' pending targets · '+esc(g.void)+' void</p>'+
      '<table class="validation-table"><thead><tr><th>Support</th><th>Training / needed</th><th>Holdout / needed</th></tr></thead><tbody>'+progress+'</tbody></table>'+
      '<p>All graded targets · game-balanced scores<br><small>Brier '+validationValue(score.brier)+' · Log loss '+validationValue(score.logLoss)+
      '<br>Average forecast '+percent(score.meanProbability)+' · Model-target hit rate '+percent(score.targetHitRate)+
      '<br>Stat projection MAE '+validationValue(errors.mae)+' over '+esc(errors.playerGames)+' player-games</small></p>'+skill+targets+
      (g.invalidResults?'<p class="error">'+esc(g.invalidResults)+' inconsistent results excluded.</p>':'')+'</article>';
  }).join('');
}
function lineCoverageMarkup(data,now=Date.now()){
 const evidence=data?.lineValidation,esc=validationEscape;
 if(!evidence)return '<details><summary>Sleeper line coverage and validation</summary><p>Exact-line tracking will populate after the next data refresh.</p></details>';
 const rows=['MLB','NFL','NBA','NHL'].map(sport=>{
  const g=evidence.sports?.[sport]||{},feed=data.platformFeed?.sportStatus?.[sport]||{};
  const age=now-Number(feed.fetchedAtEpoch)*1000;
  const status=feed.status==='UNAVAILABLE'?'Feed unavailable':!feed.fetchedAtEpoch?'Awaiting board check':age<0?'Invalid timestamp':age>900000?'Board expired':'Board fresh';
  return '<tr><td>'+sport+'</td><td>'+esc(status)+(feed.hasMore||feed.truncated||feed.degraded?' · partial board':'')+(feed.observedLines!=null?' · '+esc(feed.observedLines)+' lines':'')+'</td><td>'+esc(g.recorded||0)+'</td><td>'+esc(g.graded||0)+'</td><td>'+esc(g.eligibleTargets||0)+'</td></tr>';
 }).join('');
 const groups=(evidence.groups||[]).map(g=>'<li>'+esc(g.sport+' · '+g.prop)+' · '+esc(g.graded.playerGames)+' graded player-games · '+esc(g.review.training.playerGames)+' training / '+esc(g.review.holdout.playerGames)+' holdout · '+esc(g.eligibleTargets)+' eligible thresholds</li>').join('');
 const reasons=Object.entries(data.lineCollection?.excluded||{}).filter(([,n])=>n>0).map(([k,n])=>'<li>'+esc(k.replaceAll('_',' '))+': '+esc(n)+'</li>').join('');
 return '<details><summary>Sleeper line coverage and validation</summary><p>Fresh board lines and validated probabilities are checked separately. Only predictions frozen at observed Sleeper thresholds count here.</p><div style="overflow-x:auto"><table class="validation-table"><thead><tr><th>Sport</th><th>Board</th><th>Saved line forecasts</th><th>Graded</th><th>Validated thresholds</th></tr></thead><tbody>'+rows+'</tbody></table></div>'+(groups?'<ul>'+groups+'</ul>':'<p>Waiting for fresh lines to record exact-threshold predictions.</p>')+(reasons?'<details><summary>Why other observed lines could not be evaluated</summary><ul>'+reasons+'</ul></details>':'')+'<small>Promotion requires separate later games, exact-threshold skill checks and calibration. It does not establish betting profitability. Provider credits remain capped.</small></details>';
}
function nhlCalibrationMarkup(report){
 const esc=validationEscape,pct=v=>v==null?'—':validationValue(v*100,1)+'%';
 if(!report)return '<details class="panel"><summary>NHL estimates vs results</summary><p>Calibration comparisons will appear after the next data refresh.</p></details>';
 const labels={LIMITED_RESULTS:'Limited results',ESTIMATES_ABOVE_RESULTS:'Estimates above observed hit rate',ESTIMATES_BELOW_RESULTS:'Estimates below observed hit rate',SMALL_OBSERVED_GAP:'Small observed gap'};
 const groups=(report.groups||[]).map(g=>{
  const gap=g.gapPercentagePoints,sign=gap>0?'+':'';
  const bands=(g.bands||[]).map(b=>'<li>'+esc(b.label)+' estimates: '+pct(b.scores.meanProbability)+' average vs '+pct(b.scores.targetHitRate)+' hit rate · '+esc(b.support.playerGames)+' player-games / '+esc(b.support.games)+' games</li>').join('');
  return '<article><h3>'+esc(g.prop)+' · MORE '+esc(g.modelLine)+'</h3><small>'+esc(g.cohort==='OBSERVED_SLEEPER_LINE'?'Observed Sleeper line':'Model target · not a verified platform line')+' · '+esc(g.sourceVersion)+' · '+esc(g.calibrationVersion)+'</small><p>Average estimate <strong>'+pct(g.scores.meanProbability)+'</strong> · Observed hit rate <strong>'+pct(g.scores.targetHitRate)+'</strong><br>Gap '+(gap==null?'—':sign+validationValue(gap,1)+' percentage points')+' · '+esc(labels[g.status]||g.status)+'</p><small>'+esc(g.support.playerGames)+' graded player-games across '+esc(g.support.games)+' games · '+esc(g.pending)+' pending</small>'+(bands?'<details><summary>Compare probability bands</summary><ul>'+bands+'</ul></details>':'')+'</article>';
 }).join('');
 return '<details class="panel"><summary>NHL estimates vs results</summary><p>Positive gaps mean estimates exceeded the observed hit rate. Thresholds and model versions are compared separately; scores are balanced by game.</p>'+(groups||'<p>No NHL forecasts saved yet.</p>')+'<small>These are descriptive comparisons, including limited samples. They do not automatically validate or change probabilities.</small></details>';
}
if (typeof module !== 'undefined') module.exports = {validationMarkup, validationValue,lineCoverageMarkup,nhlCalibrationMarkup};
