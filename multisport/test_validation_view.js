const assert = require('node:assert/strict');
const {validationMarkup,validationValue} = require('./validation_view');
const minimums = {trainingPlayerGames:200,holdoutPlayerGames:100,trainingGames:25,holdoutGames:10,trainingDays:7,holdoutDays:3};
const zero = {playerGames:0,games:0,days:0,forecasts:0};
const g = {sport:'NHL',prop:'Shots <script>',status:'COLLECTING_RESULTS',recorded:{...zero,forecasts:5,playerGames:1},graded:zero,pending:5,void:0,
  review:{training:zero,holdout:zero,minimums}, scores:{brier:null,logLoss:null,meanProbability:null,targetHitRate:null},projectionErrors:{mae:null,playerGames:0}};
const html = validationMarkup({groups:[g]});
assert(html.includes('Shots &lt;script&gt;'));assert(!html.includes('<script>'));
assert(html.includes('0 / 200'));assert(html.includes('0 / 100'));
assert(html.includes('Brier —'));assert(!html.includes('0.0%'));
assert(validationMarkup({groups:[g]},'NBA').includes('No saved forecasts'));

const reviewed=JSON.parse(JSON.stringify(g));
reviewed.status='REVIEWABLE_HOLDOUT';reviewed.review.status='REVIEWABLE_HOLDOUT';
reviewed.review.forecastScores={brier:.1,logLoss:.3};reviewed.review.referenceScores={brier:.2,logLoss:.5};
reviewed.review.beatsReference=true;reviewed.review.allTargetsBeatReference=false;
reviewed.review.targetReviews=[{modelLine:2.5,status:'REVIEWABLE_TARGET',beatsReference:false,holdout:{playerGames:40}}];
const reviewedHtml=validationMarkup({groups:[reviewed]});
assert(reviewedHtml.includes('Exact targets all pass: no'));
assert(reviewedHtml.includes('2.5 · 40 holdout player-games · does not beat reference'));
assert(validationMarkup(null).includes('after the automatic feed updates'));
assert.equal(validationValue(null),'—');
console.log('Validation rendering, support counts, missing metrics, filtering and escaping checks passed.');

const {lineCoverageMarkup}=require('./validation_view');
const lineData={lineValidation:{sports:{NHL:{recorded:10,graded:4,eligibleTargets:0}},groups:[]},platformFeed:{sportStatus:{NHL:{status:'OBSERVED_BOARD',fetchedAtEpoch:Date.now()/1000,observedLines:20,truncated:true}}},lineCollection:{excluded:{'<script>':3}}};
const lineHTML=lineCoverageMarkup(lineData);assert(lineHTML.includes('Board fresh'));assert(lineHTML.includes('partial board'));assert(lineHTML.includes('20 lines'));assert(lineHTML.includes('&lt;script&gt;'));assert(!lineHTML.includes('<script>'));
assert(lineCoverageMarkup({}).includes('next data refresh'));
console.log('Observed-line coverage, partial boards, collection progress and escaping passed.');
