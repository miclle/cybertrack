// Local exercise for the production editor. No robot, speech input or remote transport.
(() => {
  const stage=document.getElementById('paper-stage');
  let revision=0, serial=0, saved=[], expires=0, playing=[], started=0;
  const names={left:'左转',right:'右转',forward:'前进',backward:'后退'};
  function clear(){
    saved=[];playing=[];stage.textContent='已停止。可以重新编排。';
  }
  function position(){
    let t=performance.now()-started;
    for(let i=0;i<playing.length;i++){
      const s=playing[i], duration=Math.max(s.move_ms,s.bubbles_ms);
      if(t<duration){
        const actions=[];
        if(t<s.move_ms) actions.push(names[s.direction]);
        if(t<s.bubbles_ms) actions.push('吹泡泡');
        stage.textContent='第 '+(i+1)+' 步 · '+actions.join('、');
        return {sequence_step:i+1,sequence_result:'running'};
      }
      if(i+1<playing.length && t<duration+200){
        stage.textContent='两步之间稍等一下…';return {sequence_step:i+1,sequence_result:'waiting'};
      }
      t-=duration+200;
    }
    if(playing.length){stage.textContent='排演结束。';playing=[];}
    return {};
  }
  function edit(d){
    if(!d || d.revision!==(saved.length?revision:0))return 'draft_changed';
    if(d.edit==='cancel'){saved=[];return 'draft_cancelled';}
    let steps=saved.slice();
    if(d.edit==='replace')steps=JSON.parse(d.steps_json);
    else {
      if(!Number.isInteger(d.step) || d.step<1 || d.step>steps.length)return 'invalid_plan';
      if(d.edit==='remove_step')steps.splice(d.step-1,1);
      else if(d.edit==='replace_step'){
        const next=JSON.parse(d.steps_json);
        if(next.length!==1)return 'invalid_plan';
        steps[d.step-1]=next[0];
      }else return 'invalid_plan';
    }
    if(!Array.isArray(steps)||!steps.length||steps.length>16||!steps.every(validShowStep))return 'invalid_plan';
    saved=steps;revision++;expires=performance.now()+300000;return 'draft_saved';
  }
  window.fetch=async (path,options)=>{
    const body=JSON.parse(options.body||'{}');
    if(path==='/api/pair')return Response.json({result:'ok',token:'offline-rehearsal'});
    if(performance.now()>=expires)saved=[];
    position();
    let result='ok';
    if(path==='/api/stop'||path==='/api/release')clear();
    else if(path==='/api/action'){
      if(playing.length)result='not_ready_or_busy';
      else if(body.operation==='show_edit')result=edit(body.draft);
      else if(body.operation==='show_confirm'){
        if(!saved.length || body.revision!==revision)result='draft_changed';
        else {playing=saved;saved=[];started=performance.now();result='accepted';}
      }else result='invalid_request';
    }else if(path!=='/api/state')throw Error('Offline rehearsal only');
    const step=position(), active=playing.length>0;
    return Response.json({result,request_sequence:++serial,window:serial,state:active?'ACTIVE':'STOPPED',
      fault:'none',boot_held:false,capabilities:{show_draft:true},sequence_active:active,
      sequence_source:active?'web':'none',sequence_steps:playing.length,...step,
      show_draft:{active:!!saved.length,revision:saved.length?revision:0,steps:saved,
        expires_in_ms:saved.length?Math.max(0,expires-performance.now()):0}});
  };
  setInterval(()=>{if(playing.length)position();},50);
})();
