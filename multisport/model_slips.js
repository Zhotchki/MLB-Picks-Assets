/* Shared bounded ranking; callers supply independently eligible pools. */
function modelSlips(data,size,now=Date.now(),sports='All sports'){
 const selected=Array.isArray(sports)?new Set(sports):sports==='All sports'?null:new Set([sports]);
 const pool=forecastPool(data,now).filter(r=>r.scheduleVerified===true&&r.direction==='MORE'&&Number.isFinite(r.target)&&(!selected||selected.has(r.sport)));
 return rankSlipPool(pool,size).map(s=>({...s,kind:'MODEL_TEST',actionable:false}));
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
function rankSlipPool(pool,size){
 const unique=[...new Map([...pool].sort((a,b)=>a.probability-b.probability).map(r=>[slipPickKey(r),r])).values()],out=[],uses=new Map(),seen=new Set();
 for(let slot=0;slot<3;slot++){
  const candidates=rankSlipCandidates(unique.filter(r=>(uses.get(slipPickKey(r))||0)<2),size);
  const next=candidates.find(s=>!seen.has(s.legs.map(slipPickKey).sort().join('|')));if(!next)break;
  out.push(next);seen.add(next.legs.map(slipPickKey).sort().join('|'));
  for(const r of next.legs){const k=slipPickKey(r);uses.set(k,(uses.get(k)||0)+1);}
 }return out;
}
function rankSlipCandidates(pool,size){
 size=Number(size);if(![2,3,4,5,6,8].includes(size))return [];
 const groups=new Map();
 for(const r of pool){const key=forecastGameKey(r);if(!groups.has(key))groups.set(key,[]);groups.get(key).push(r);}
 if(groups.size<size)return [];
 // At most three candidates per player/game: sufficient alternatives for three slips.
 const events=[...groups].sort(([a],[b])=>a.localeCompare(b)).map(([,rows])=>{
  const players=new Map();for(const r of rows.sort((a,b)=>b.probability-a.probability||String(a.id).localeCompare(String(b.id)))){
   const key=r.sport+':'+r.playerId;if(!players.has(key))players.set(key,[]);if(players.get(key).length<3)players.get(key).push(r);
  }return [...players.values()].flat().sort((a,b)=>b.probability-a.probability).slice(0,24);
 });
 let states=Array.from({length:size+1},()=>[]);states[0]=[{legs:[],probability:1,players:new Set()}];
 for(const rows of events){
  for(let n=size;n>0;n--){const next=[...states[n]];
   for(const s of states[n-1])for(const r of rows){const key=r.sport+':'+r.playerId;if(s.players.has(key))continue;
    next.push({legs:[...s.legs,r],probability:s.probability*r.probability,players:new Set([...s.players,key])});
   }
   next.sort((a,b)=>b.probability-a.probability);states[n]=next.slice(0,200);
  }
 }
 return states[size].map(({legs,probability})=>({legs,probability,searchComplete:false}));
}
if(typeof module!=='undefined')module.exports={modelSlips,rankSlipPool,slipPickKey,limitSlipReuse};
