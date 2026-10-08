/* Upcoming model forecasts, grouped by player AND verified game. */
function forecastPool(data,now=Date.now()){
  const age=now-Date.parse(data?.updatedAt);
  if(!Number.isFinite(age)||age>45*60000||age< -5*60000)return [];
  return (data.picks||[]).filter(r=>data.sports?.[r.sport]?.sourceStatus==='CURRENT'&&
    Number.isFinite(Date.parse(r.startTime))&&Date.parse(r.startTime)>now&&
    r.playerId!=null&&r.gameId!=null&&Number.isFinite(r.probability)&&r.probability>0&&r.probability<1);
}
function forecastGameKey(r){return JSON.stringify([r.sport,String(r.gameId)]);}
function playerCardKey(r){return JSON.stringify([r.sport,String(r.playerId),String(r.gameId)]);}
function playerGroups(data,filters={},now=Date.now()){
  const normalize=v=>String(v??'').normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
  const query=normalize(filters.search).trim(),minimum=Number(filters.minimum)||0,groups=new Map();
  for(const r of forecastPool(data,now)){
    if(filters.sport&&filters.sport!=='All sports'&&r.sport!==filters.sport)continue;
    if(filters.prop&&filters.prop!=='All props'&&r.prop!==filters.prop)continue;
    if(filters.game&&filters.game!=='All games'&&forecastGameKey(r)!==filters.game)continue;
    if(r.probability*100<minimum||!normalize([r.player,r.team,r.opponent].join(' ')).includes(query))continue;
    const key=playerCardKey(r);
    if(!groups.has(key))groups.set(key,[]);
    groups.get(key).push(r);
  }
  const compare=(a,b)=>b.probability-a.probability||String(a.prop).localeCompare(String(b.prop))||String(a.id).localeCompare(String(b.id));
  return [...groups.values()].map(rows=>rows.sort(compare)).sort((a,b)=>compare(a[0],b[0])||String(a[0].player).localeCompare(String(b[0].player)));
}
function playerCardsMarkup(groups,openKeys=new Set()){
  const escape=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const percent=v=>(v*100).toFixed(1)+'%';
  const prop=r=>'<div class="prop">'+escape(r.prop)+' · '+escape(r.sport==='NFL'?'MORE '+r.modelLine:r.target+'+')+' <strong>'+percent(r.probability)+'</strong><br><small>Projection '+escape(Number.isFinite(r.projection)?r.projection.toFixed(2):'—')+' · '+escape(r.samples)+(r.sport==='MLB'?' calibration samples':' historical games')+'</small>'+(r.probabilityStatus==='UNVALIDATED_BASELINE'?'<br><small>Unvalidated baseline · not eligible for playable slips</small>':'')+(r.playingTimeUnit&&Number.isFinite(r.expectedPlayingTime)?'<br><small>Expected '+(r.sport==='NHL'?'ice time ':'playing time ')+r.expectedPlayingTime.toFixed(1)+' minutes</small>':'')+'</div>';
  return groups.map(rows=>{
    const r=rows[0];
    const key=playerCardKey(r);
    return '<details class="card" data-player-key="'+escape(key)+'"'+(openKeys.has(key)?' open=""':'')+'><summary><div><div class="name">'+escape(r.player)+'</div><div class="best-pick">'+escape(r.prop)+' · '+escape(r.sport==='NFL'?'MORE '+r.modelLine:r.target+'+')+'</div><small>'+escape(r.sport+' · '+r.team+' vs '+r.opponent)+'<br>'+escape(new Date(r.startTime).toLocaleString())+(r.probabilityStatus==='UNVALIDATED_BASELINE'?'<br>Unvalidated baseline · not eligible for slips':'')+'</small></div><div class="prob">'+percent(r.probability)+'</div></summary>'+prop(r)+'<small>'+escape(r.lineupStatus)+'</small><div class="extra">'+(rows.slice(1).map(prop).join('')||'<small>No additional forecasts matching these filters</small>')+'</div></details>';
  }).join('');
}
if(typeof module!=='undefined')module.exports={forecastPool,forecastGameKey,playerCardKey,playerGroups,playerCardsMarkup};
