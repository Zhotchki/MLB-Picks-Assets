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
assert(validationMarkup(null).includes('after the automatic feed updates'));
assert.equal(validationValue(null),'—');
console.log('Validation rendering, support counts, missing metrics, filtering and escaping checks passed.');
