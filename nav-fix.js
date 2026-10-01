(function(){
  function activate(name){
    document.querySelectorAll('.screen').forEach(function(s){
      s.classList.toggle('active',s.getAttribute('data-screen')===name);
    });
    document.querySelectorAll('.navbtn').forEach(function(b){
      b.classList.toggle('active',b.getAttribute('data-target')===name);
    });
    try{window.scrollTo(0,0)}catch(e){}
    if(typeof window.mlbLoadSection==='function') window.mlbLoadSection(name);
  }
  function bind(){
    document.querySelectorAll('.navbtn').forEach(function(btn){
      if(btn.__mlbBound)return;
      btn.__mlbBound=true;
      btn.addEventListener('click',function(e){
        e.preventDefault();
        e.stopPropagation();
        activate(btn.getAttribute('data-target'));
      },true);
    });
  }
  bind();
  window.addEventListener('DOMContentLoaded',bind);
  window.MLBNav={activate:activate};
})();