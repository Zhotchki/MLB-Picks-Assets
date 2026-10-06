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
      '<br><small>Better on both Brier and log loss: '+(review.beatsReference?'yes':'no')+'. This comparison does not enable playable offers.</small></p>' : '';
    return '<article class="panel"><h2>'+esc(g.sport)+' · '+esc(g.prop)+'</h2><p>'+esc(statuses[g.status] || g.status)+
      '</p><small>'+esc(g.sourceVersion || 'No source forecasts yet')+(g.modelVersion?' · '+esc(g.modelVersion):'')+'</small><p>'+esc(g.recorded.forecasts)+
      ' saved targets · '+esc(g.recorded.playerGames)+' player-games<br>'+esc(g.graded.playerGames)+' graded player-games · '+esc(g.pending)+' pending targets · '+esc(g.void)+' void</p>'+
      '<table class="validation-table"><thead><tr><th>Support</th><th>Training / needed</th><th>Holdout / needed</th></tr></thead><tbody>'+progress+'</tbody></table>'+
      '<p>All graded targets · game-balanced scores<br><small>Brier '+validationValue(score.brier)+' · Log loss '+validationValue(score.logLoss)+
      '<br>Average forecast '+percent(score.meanProbability)+' · Model-target hit rate '+percent(score.targetHitRate)+
      '<br>Stat projection MAE '+validationValue(errors.mae)+' over '+esc(errors.playerGames)+' player-games</small></p>'+skill+
      (g.invalidResults?'<p class="error">'+esc(g.invalidResults)+' inconsistent results excluded.</p>':'')+'</article>';
  }).join('');
}
if (typeof module !== 'undefined') module.exports = {validationMarkup, validationValue};
