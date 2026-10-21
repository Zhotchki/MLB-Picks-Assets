/* Shared bounded ranking; callers supply independently eligible pools. */
function modelSlips(data,size,now=Date.now(),sport='All sports'){
 const pool=forecastPool(data,now).filter(r=>r.scheduleVerified===true&&r.direction==='MORE'&&Number.isFinite(r.target)&&(sport==='All sports'||r.sport===sport));
 return rankSlipPool(pool,size).map(s=>({...s,kind:'MODEL_TEST',actionable:false}));
}
function rankSlipPool(pool,size){
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
 return states[size].slice(0,3).map(({legs,probability})=>({legs,probability,searchComplete:false}));
}
if(typeof module!=='undefined')module.exports={modelSlips,rankSlipPool};
