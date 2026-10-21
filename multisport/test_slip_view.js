const fs=require('fs'),vm=require('vm'),assert=require('assert');
const path=require('path'),root=__dirname,nodes={};
const node=id=>nodes[id]||(nodes[id]={value:id==='#size'?'4':id==='#playerSearch'?'':id==='#playerProp'?'All props':id==='#playerGame'?'All games':id==='#playerMinimum'?'0':'All sports',options:id==='#size'?[2,3,4,5,6,8].map(value=>({value:String(value)})):[],innerHTML:'',textContent:'',hidden:false,disabled:false});
const context=vm.createContext({document:{querySelector:node,querySelectorAll:()=>[],addEventListener:()=>{}},fetch:()=>new Promise(()=>{}),setInterval:()=>{},Date});
for(const file of ['player_view.js','model_slips.js','eligibility.js','validation_view.js'])vm.runInContext(fs.readFileSync(path.join(root,file),'utf8'),context);
const html=fs.readFileSync(path.join(root,'index.html'),'utf8');
for(const match of html.matchAll(/<script>([\s\S]*?)<\/script>/g))vm.runInContext(match[1],context);
const now=Date.now(),leg=id=>({sport:'MLB',gameId:id,playerId:id,player:'<Player '+id+'>',prop:'Hits',platformLine:0.5,probability:0.7,platform:'Sleeper',actionable:true,requiresPlatformReview:true,platformOfferType:'unreported',kickoffSource:'OFFICIAL_SCHEDULE',startTime:new Date(now+3600000).toISOString(),offerObservedAt:new Date(now-1000).toISOString()});
const legs=[leg(1),leg(2)];
context.fixture={updatedAt:new Date(now-1000).toISOString(),sourceStatus:'CURRENT',sports:{MLB:{status:'LIVE_FORECASTS',sourceStatus:'CURRENT'}},picks:[],results:{recorded:0,graded:0,frozenPredictionMetrics:{brier:null}},model:{version:'fixture'},platformFeed:{status:'CONFIGURED',sportStatus:{MLB:{status:'OBSERVED_BOARD',fetchedAtEpoch:now/1000}},nextRefreshAt:new Date(now+3600000).toISOString(),refreshReason:'SCHEDULED'},offerCounts:{observed:5,matched:2,missingOfferType:2,missingKickoff:2,excluded:{unmatched_model_line:2,expired_line:1}},offers:legs,slips:{'2':[{probability:0.49,legs}]}};
vm.runInContext('data=fixture;render()',context);
assert.equal(node('#generate').disabled,false);
assert(node('#slipSupport').innerHTML.includes('2 fresh exact-line offers · 2 players · 2 separate games'));
assert(node('#slipSupport').innerHTML.includes('No probability for that exact line'));
assert(node('#slipSupport').innerHTML.includes('Expired individual lines'));
assert.equal(node('#size').value,'2');
assert.equal(node('#size').options.find(option=>option.value==='4').disabled,true);
assert(node('#feedTiming').textContent.includes('Next matched line expires in'));
assert(node('#feedTiming').textContent.includes('Next automatic board check after'));
node('#generate').onclick();
assert(node('#slipCards').innerHTML.includes('49.0%'));
assert(node('#slipCards').innerHTML.includes('Review in Sleeper'));
assert(node('#slipCards').innerHTML.includes('Kickoff verified from official schedule.'));
assert(node('#slipCards').innerHTML.includes('&lt;Player'));
assert(!node('#slipCards').innerHTML.includes('Source-declared standard offer.'));
assert(node('#slipMessage').textContent.includes('2 have an unreported offer type'));
context.fixture.slips['2'][0].searchComplete=true;node('#generate').onclick();
assert(node('#slipCards').innerHTML.includes('Exact ranking of current matched offers'));
context.fixture.slips['2'][0].searchComplete=false;node('#generate').onclick();
assert(node('#slipCards').innerHTML.includes('Bounded ranking search'));
for(const row of legs)row.offerObservedAt=new Date(now-16*60000).toISOString();
vm.runInContext('expireDisplayedSlips()',context);
assert.equal(node('#generate').disabled,true);
assert(!node('#slipCards').innerHTML.includes('49.0%'));
context.fixture.platformFeed.sportStatus.MLB.httpStatus=401;
vm.runInContext('render()',context);
assert(node('#slipMessage').textContent.includes('HTTP 401'));
context.fixture.platformFeed.refreshMode='PREGAME_WINDOWS';context.fixture.platformFeed.refreshReason='DAILY_BUDGET';vm.runInContext('render()',context);
assert(node('#feedTiming').textContent.includes('Daily allowance used.'));
assert(node('#feedTiming').textContent.includes('Checks target upcoming game windows.'));
assert(node('#slipSupport').innerHTML.includes('0 fresh exact-line offers · 0 players · 0 separate games'));
context.fixture.sports.MLB.gradingStatus='PARTIAL_RESULT_SOURCE';context.fixture.sports.MLB.gradingGamesUnavailable=1;vm.runInContext('render()',context);
assert(node('#gradingHealth').textContent.includes('MLB: 1 game-result source unavailable'));
assert(node('#gradingHealth').textContent.includes('Affected forecasts stay pending'));
context.fixture.sports.MLB.gradingStatus='CURRENT';vm.runInContext('render()',context);assert.equal(node('#gradingHealth').textContent,'');
console.log('Slip rendering, leg availability, board timing, review flags, expiry and provider errors passed.');

context.fixture.platformFeed.plannedChecks=[{sport:'NFL',checkAt:new Date(now+7200000).toISOString(),games:8},{sport:'MLB',checkAt:new Date(now+3600000).toISOString(),games:1},{sport:'NHL',checkAt:new Date(now-3600000).toISOString(),games:2},{sport:'<NBA>',checkAt:'invalid',games:1}];
vm.runInContext('render()',context);
assert(node('#boardSchedule').innerHTML.includes('Upcoming automatic board checks'));
assert(node('#boardSchedule').innerHTML.indexOf('MLB')<node('#boardSchedule').innerHTML.indexOf('NFL'));
assert(!node('#boardSchedule').innerHTML.includes('NHL'));
assert(!node('#boardSchedule').innerHTML.includes('NBA'));
assert(node('#boardSchedule').innerHTML.includes('8 games'));
assert(node('#boardSchedule').innerHTML.includes('1 game</li>'));
context.fixture.platformFeed.plannedChecks=[];vm.runInContext('render()',context);assert.equal(node('#boardSchedule').innerHTML,'');
console.log('Upcoming board schedule ordering, stale/invalid exclusion and empty state passed.');

context.fixture.weeklyTracking={currentWeek:'2030-W01',summary:[{week:'2030-W01',size:2,allHit:1,missed:0,pending:0,voided:0}],slips:[{week:'2030-W01',size:2,slot:1,status:'ALL_HIT',allHit:true,hits:2,misses:0,voids:0,pending:0,probability:.49,capturedAt:new Date(now).toISOString(),searchComplete:true,legs:[{player:'<Test Player>',sport:'NHL',prop:'Shots',usesModelLine:true,modelLine:.5,probability:.7,status:'HIT',actual:0,startTime:new Date(now).toISOString(),platformEligible:false}]}]};
node('#weeklySize').value='2';vm.runInContext('renderWeekly()',context);
assert(node('#weeklySummary').textContent.includes('1 all-hit'));
assert(node('#weeklyCards').innerHTML.includes('100% HIT'));
assert(node('#weeklyCards').innerHTML.includes('&lt;Test Player&gt;'));
assert(node('#weeklyCards').innerHTML.includes('Actual: 0'));
assert(node('#weeklyCards').innerHTML.includes('Unvalidated baseline'));
assert(node('#weeklyCards').innerHTML.includes('Paper evaluation only'));
console.log('Weekly model slips, all-hit labels, escaping and zero actuals passed.');

// Model previews remain usable with zero live offers; start times and stale sources still gate.
const paperLeg=(id,p=.8)=>({...leg(id),id:'forecast-'+id,target:1,modelLine:.5,direction:'MORE',scheduleVerified:true,probability:p,probabilityStatus:'UNVALIDATED_BASELINE',platformEligible:false});
context.fixture.picks=[paperLeg(10),paperLeg(11),paperLeg(12),paperLeg(13)];
context.fixture.offers=[];context.fixture.slips={};node('#modelSize').value='4';
vm.runInContext('render();renderModelCards()',context);
assert.equal(node('#generateModel').disabled,false);
assert(node('#modelCards').innerHTML.includes('Model preview'));
assert(node('#modelCards').innerHTML.includes('Unvalidated baseline'));
assert.equal(node('#generate').disabled,true);
vm.runInContext(`
const paper=modelSlips(data,2);if(paper.length!==3)throw Error('Expected three alternatives');
for(const s of paper){if(new Set(s.legs.map(forecastGameKey)).size!==2)throw Error('Repeated game');if(s.actionable!==false)throw Error('Live contamination');}
`,context);
context.fixture.picks[1].playerId=10;context.fixture.picks[2].scheduleVerified=false;context.fixture.picks[3].startTime=new Date(now-1000).toISOString();
assert.equal(vm.runInContext('modelSlips(data,2).length',context),0);
context.fixture.updatedAt=new Date(now-46*60000).toISOString();
assert.equal(vm.runInContext('modelSlips(data,2).length',context),0);
console.log('On-demand model generation, unvalidated labels, unique players/games, started games and stale feed passed.');

// Sport choice filters before ranking, including live pools absent from cached mixed slips.
context.fixture.updatedAt=new Date(now-1000).toISOString();
context.fixture.sports.NFL={sourceStatus:'CURRENT',status:'LIVE_FORECASTS'};
context.fixture.picks=[paperLeg(21),paperLeg(22),{...paperLeg(23),sport:'NFL'},{...paperLeg(24),sport:'NFL'}];
node('#slipSport').value='NFL';node('#modelSize').value='4';
node('#slipSport').onchange();
assert.equal(node('#modelSize').value,'2');
assert.equal(node('#modelCards').innerHTML,'');
node('#generateModel').onclick();
assert(node('#modelCards').innerHTML.includes('NFL ·'));
assert(!node('#modelCards').innerHTML.includes('MLB ·'));
assert(node('#modelAvailability').textContent.includes('NFL · Available sizes: 2'));
context.fixture.offers=[leg(21),leg(22),{...leg(23),sport:'NFL'},{...leg(24),sport:'NFL'}];
context.fixture.slips={};vm.runInContext('render()',context);
assert.equal(node('#generate').disabled,false);
node('#generate').onclick();
assert(node('#slipCards').innerHTML.includes('NFL ·'));
assert(!node('#slipCards').innerHTML.includes('MLB ·'));
assert(node('#slipSupport').innerHTML.includes('2 fresh exact-line offers'));
context.fixture.offers[3].offerObservedAt=new Date(now-16*60000).toISOString();vm.runInContext('expireDisplayedSlips()',context);
assert.equal(node('#generate').disabled,true);
assert(!node('#slipCards').innerHTML.includes('NFL ·'));
node('#slipSport').value='NBA';node('#slipSport').onchange();
assert.equal(node('#generateModel').disabled,true);
assert.equal(node('#modelCards').innerHTML,'');
assert.equal(node('#slipCards').innerHTML,'');
assert(node('#modelAvailability').textContent.includes('No NBA model slips available'));
node('#slipSport').value='All sports';node('#slipSport').onchange();
assert.equal(node('#generateModel').disabled,false);
assert.equal(vm.runInContext('modelSlips(data,4).length',context),1);
console.log('Sport-specific model/live ranking, mixed mode, size fallback, expiry and empty-state clearing passed.');

// Reuse is counted by the exact pick, across the whole generated batch.
context.reusePool=Array.from({length:16},(_,i)=>({...paperLeg(100+i),probability:.95-i*.01}));
vm.runInContext(`
for(const size of [2,4,8]){
 const batch=rankSlipPool(reusePool,size),counts=new Map();if(batch.length!==3)throw Error('Missing alternatives');
 for(const s of batch)for(const r of s.legs){const k=slipPickKey(r);counts.set(k,(counts.get(k)||0)+1);}
 if([...counts.values()].some(n=>n>2))throw Error('Pick used three times');
}
const aliases=[reusePool[0],{...reusePool[0],id:'different-model-id'},...reusePool.slice(1)];
const aliasCounts=new Map();for(const s of rankSlipPool(aliases,4))for(const r of s.legs){const k=slipPickKey(r);aliasCounts.set(k,(aliasCounts.get(k)||0)+1);}
if([...aliasCounts.values()].some(n=>n>2))throw Error('Alias bypassed cap');
if(rankSlipPool(reusePool.slice(0,2),2).length!==1)throw Error('Duplicate slips');
`,context);
console.log('Two-use pick cap, alternate-pick reranking, aliases and exhausted pools passed.');
