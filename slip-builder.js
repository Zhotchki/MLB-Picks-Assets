(function(){
  function $(s){return document.querySelector(s)}
  function esc(v){return window.MLBApp&&window.MLBApp.esc?window.MLBApp.esc(v):String(v==null?'':v)}
  function pct(v){return window.MLBApp&&window.MLBApp.pct?window.MLBApp.pct(v):(Number(v)*100).toFixed(1)+'%'}
  function prob(r){const p=Number(r['Adjusted Probability']||r['Probability']);return Number.isFinite(p)&&p>0&&p<1?p:null}
  function eligible(){
    const d=window.MLBApp&&window.MLBApp.getData?window.MLBApp.getData():null;
    return ((d&&d.picks)||[]).filter(function(r){
      const p=prob(r);
      const injury=String(r['Injury Status']||'').toUpperCase();
      const gameState=String(r['Game State']||'').toUpperCase();
      const confidence=String(r.Confidence||'').toUpperCase();
      return !['LIVE','FINAL'].includes(gameState) && p!==null && Number(r['Probability Samples']||0)>=25 &&
        confidence!=='CALIBRATING' && !/IL|INJURED|OUT|SUSPENDED/.test(injury);
    });
  }
  function bestByPlayerProp(rows){
    const m=new Map();
    rows.forEach(function(r){const k=String(r.Player||'')+'|'+String(r.Prop||'');if(!m.has(k)||prob(r)>prob(m.get(k)))m.set(k,r)});
    return Array.from(m.values()).sort(function(a,b){return prob(b)-prob(a)});
  }
  function buildOne(pool,size,offset,useCount){
    const chosen=[],players=new Set();
    const rotated=pool.slice(offset).concat(pool.slice(0,offset));
    while(chosen.length<size){
      let best=null,bestScore=-1e9;
      for(let i=0;i<rotated.length;i++){
        const r=rotated[i], player=String(r.Player||'');
        if(players.has(player))continue;
        const p=prob(r); if(p===null)continue;
        const prior=useCount[player]||0;
        const confidence=String(r.Confidence||'').toUpperCase();
        const confidenceBonus=confidence==='HIGH'?0.02:confidence==='MEDIUM'?0.01:0;
        const score=Math.log(p)+confidenceBonus-prior*0.02;
        if(score>bestScore){bestScore=score;best=r}
      }
      if(!best)break;
      chosen.push(best);players.add(String(best.Player||''));
      useCount[String(best.Player||'')]=(useCount[String(best.Player||'')]||0)+1;
      rotated.splice(rotated.indexOf(best),1);
    }
    if(chosen.length!==size)return null;
    const combined=chosen.reduce(function(a,r){return a*prob(r)},1);
    return {legs:chosen,probability:combined,multiplier:1/combined};
  }
  function money(n){return '$'+Number(n).toFixed(2)}
  function render(){
    const sizeVal=$('#slipSize').value;
    const sizes=sizeVal==='all'?[4,6,8]:[Number(sizeVal)];
    const count=Math.max(1,Math.min(10,Number($('#slipCount').value||5)));
    const bet=Math.max(1,Math.min(10,Number($('#slipBet').value||5)));
    const pool=bestByPlayerProp(eligible());
    const slips=[],useCount={};
    sizes.forEach(function(size){
      if(pool.length<size)return;
      for(let s=0;s<count;s++){
        const offset=(s*Math.max(1,Math.floor(pool.length/count)))%pool.length;
        const slip=buildOne(pool,size,offset,useCount);
        if(slip){slip.size=size;slip.bet=bet;slip.payout=bet*slip.multiplier;slips.push(slip)}
      }
    });
    const summary=$('#slipsSummary'), list=$('#slipsList');
    if(!slips.length){summary.innerHTML='';list.innerHTML='<div class="empty">Not enough eligible picks to generate the requested slips yet.</div>';return}
    const avg=slips.reduce(function(a,s){return a+s.probability},0)/slips.length;
    summary.innerHTML='<article class="card"><div class="name">'+slips.length+' generated slips</div><div class="why">Average estimated combined probability: <strong>'+pct(avg)+'</strong> · Total stake: <strong>'+money(slips.length*bet)+'</strong></div></article>';
    list.innerHTML=slips.map(function(s,idx){
      const legs=s.legs.map(function(r,j){
        const th=r['Probability Threshold']!==''&&r['Probability Threshold']!=null?String(r['Probability Threshold'])+'+ ':'';
        return '<div class="slipleg"><div class="legnum">'+(j+1)+'</div><div class="legmain"><div class="legplayer">'+esc(r.Player)+'</div><div class="legsub">'+esc(r.Prop)+' · '+th+esc(r.Team)+' vs '+esc(r.Opponent)+'</div></div><div class="legprob">'+pct(prob(r))+'</div></div>';
      }).join('');
      return '<article class="slipcard"><div class="sliphead"><div><div class="sliptitle">Slip '+(idx+1)+' · '+s.size+' legs</div><div class="slipmeta">'+money(s.bet)+' stake · no duplicate players</div></div><span class="badge high">'+pct(s.probability)+'</span></div>'+
        '<div class="slipmetrics"><div class="slipmetric"><div class="k">COMBINED PROBABILITY</div><div class="v">'+pct(s.probability)+'</div></div><div class="slipmetric"><div class="k">EXPECTED MULTIPLIER</div><div class="v">'+s.multiplier.toFixed(2)+'×</div></div><div class="slipmetric"><div class="k">PREDICTED PAYOUT</div><div class="v">'+money(s.payout)+'</div></div></div>'+legs+
        '<div class="slipnote" style="margin-top:8px">Higher-confidence picks are preferred first; lower-confidence valid picks can fill remaining legs. Combined probability assumes leg independence; correlated outcomes can change the true joint probability. Predicted payout is model-implied, not Sleeper’s posted payout.</div></article>';
    }).join('');
  }
  const btn=$('#buildSlips');if(btn)btn.addEventListener('click',render);
})();