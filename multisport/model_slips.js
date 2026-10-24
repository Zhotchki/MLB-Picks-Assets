/* Shared bounded ranking; callers supply independently eligible pools. */
const modelSlipCache=new WeakMap();
function modelPoolFingerprint(pool){return JSON.stringify(pool.map(r=>[r.id,slipPickKey(r),r.probability,r.startTime]));}
function modelSlipPool(data,now,sports){
 const selected=Array.isArray(sports)?new Set(sports):sports==='All sports'?null:new Set([sports]);
 return {pool:forecastPool(data,now).filter(r=>r.scheduleVerified===true&&r.direction==='MORE'&&Number.isFinite(r.target)&&(!selected||selected.has(r.sport))),minSports:!selected||selected.size>1?2:1};
}
function modelSlips(data,size,now=Date.now(),sports='All sports'){
 const {pool,minSports}=modelSlipPool(data,now,sports);
 const fingerprint=modelPoolFingerprint(pool);
 if(!modelSlipCache.has(data))modelSlipCache.set(data,new Map());const cache=modelSlipCache.get(data),key=JSON.stringify([sports,Number(size),minSports]);
 const saved=cache.get(key);if(saved?.fingerprint===fingerprint)return saved.slips;
 const slips=rankSlipPool(pool,size,minSports).map(s=>({...s,kind:'MODEL_TEST',actionable:false}));cache.set(key,{fingerprint,slips});return slips;
}
function modelSlipSizes(data,now=Date.now(),sports='All sports'){
 const {pool,minSports}=modelSlipPool(data,now,sports),fingerprint=modelPoolFingerprint(pool);
 if(!modelSlipCache.has(data))modelSlipCache.set(data,new Map());const cache=modelSlipCache.get(data),key=JSON.stringify([sports,'sizes',minSports]);
 const saved=cache.get(key);if(saved?.fingerprint===fingerprint)return saved.sizes;
 const sets=rankSlipCandidates(pool,8,minSports,true),sizes=[2,3,4,5,6,8].filter(size=>sets[size]?.length);cache.set(key,{fingerprint,sizes});return sizes;
}
function slipPickKey(r){
 const line=Number.isFinite(r.platformLine)?r.platformLine:Number.isFinite(r.modelLine)?r.modelLine:Number.isFinite(r.target)?r.target-.5:null;
 return JSON.stringify([r.sport,String(r.gameId),String(r.playerId),r.prop,r.direction||'MORE',line]);
}
function limitSlipReuse(slips,count=3){
 const uses=new Map(),seen=new Set(),out=[];
 for(const s of slips){const keys=s.legs.map(slipPickKey),sig=[...keys].sort().join('|');
  if(seen.has(sig)||keys.some(k=>(uses.get(k)||0)>=2))continue;
  out.push(s);seen.add(sig);keys.forEach(k=>uses.set(k,(uses.get(k)||0)+1));if(out.length>=count)break;
 }return out;
}
function rankSlipPool(pool,size,minSports=1){
 const unique=[...new Map([...pool].sort((a,b)=>a.probability-b.probability).map(r=>[slipPickKey(r),r])).values()],out=[],uses=new Map(),seen=new Set();
 for(let slot=0;slot<3;slot++){
  const candidates=rankSlipCandidates(unique.filter(r=>(uses.get(slipPickKey(r))||0)<2),size,minSports);
  const next=candidates.find(s=>!seen.has(s.legs.map(slipPickKey).sort().join('|')));if(!next)break;
  out.push(next);seen.add(next.legs.map(slipPickKey).sort().join('|'));
  for(const r of next.legs){const k=slipPickKey(r);uses.set(k,(uses.get(k)||0)+1);}
 }return out;
}
function rankSlipCandidates(pool,size,minSports=1,allSizes=false){
 size=Number(size);if(![2,3,4,5,6,8].includes(size))return [];
 const groups=new Map();
 for(const r of pool){const key=forecastGameKey(r);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);}
 if((!allSizes&&groups.size<size)||new Set(pool.map(r=>r.sport)).size<minSports)return allSizes?{}:[];
 // At most three candidates per player/game: sufficient alternatives for three slips.
 const events=[...groups].sort(([a],[b])=>a.localeCompare(b)).map(([,rows])=>{
  const players=new Map();for(const r of rows.sort((a,b)=>b.probability-a.probability||String(a.id).localeCompare(String(b.id)))){
   const key=r.sport+':'+r.playerId;if(!players.has(key))players.set(key,[]);if(players.get(key).length<3)players.get(key).push(r);
  }return [...players.values()].flat().sort((a,b)=>b.probability-a.probability).slice(0,24);
 });
 let states=Array.from({length:size+1},()=>[]);states[0]=[{legs:[],probability:1,players:new Set(),sports:new Set()}];
 for(const rows of events){
  for(let n=size;n>0;n--){const next=[...states[n]];
   for(const s of states[n-1])for(const r of rows){const key=r.sport+':'+r.playerId;if(s.players.has(key))continue;
    next.push({legs:[...s.legs,r],probability:s.probability*r.probability,players:new Set([...s.players,key]),sports:new Set([...s.sports,r.sport])});
   }
   next.sort((a,b)=>b.probability-a.probability);
   // Preserve single-sport prefixes separately so a lower-probability sport is
   // not pruned before it can join a mixed slip. Completed mixes share a bucket.
   const buckets=new Map();for(const s of next){const key=minSports>1?(s.sports.size>=minSports?'mixed':[...s.sports].sort().join(',')):'all';if(!buckets.has(key))buckets.set(key,[]);if(buckets.get(key).length<200)buckets.get(key).push(s);}
   states[n]=[...buckets.values()].flat();
  }
 }
 const result=n=>states[n].filter(s=>s.sports.size>=minSports).sort((a,b)=>b.probability-a.probability).map(({legs,probability})=>({legs,probability,searchComplete:false}));
 return allSizes?Object.fromEntries([2,3,4,5,6,8].map(n=>[n,result(n)])):result(size);
}
if(typeof module!=='undefined')module.exports={modelSlips,modelSlipSizes,rankSlipPool,slipPickKey,limitSlipReuse};
