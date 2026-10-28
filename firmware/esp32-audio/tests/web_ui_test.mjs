// Execute the shipped page script with a fake DOM/transport, without hardware.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const html=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const flush=()=>new Promise(r=>setImmediate(r));
assert(!html.includes('id="pairing"') && !html.includes('id="combined"') && !html.includes('id="release"'));
function harness(){
 const element=()=>({value:'1000',disabled:true,style:{},events:{},classList:{toggle(){}},setAttribute(){},captured:false,
  setPointerCapture(){this.captured=true;},hasPointerCapture(){return this.captured;},releasePointerCapture(){this.captured=false;},
  getBoundingClientRect(){return {left:0,top:0,right:100,bottom:100};},addEventListener(n,f){this.events[n]=f;}});
 const ids=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],element()]));
 const buttons=['forward','backward','left','right'].map(direction=>({...element(),dataset:{direction}}));
 const events={},pending=[],sent=[],timers=new Map();let timerId=0, clock=0;
 for(const kind of ['water','bubbles']) ids[kind+'-hold'].dataset={hold:kind};
 const effectButtons=[];
 for(const kind of ['water','bubbles','ignition','frenzy']) for(const sec of (kind==='frenzy'?[5,10,30]:kind==='ignition'?[1,3,5]:[1,3,5,10,30])) {
   const b=ids[sec===1?kind:kind+'-'+sec];b.dataset={effect:kind,duration:String(sec*1000)};effectButtons.push(b);
 }
 const document={hidden:false,getElementById:id=>ids[id],querySelectorAll:q=>q.includes('[data-hold]')?[...buttons,ids['water-hold'],ids['bubbles-hold']]:q==='[data-effect]'?effectButtons:q.startsWith('[data-effect=')?effectButtons.filter(b=>q.includes(b.dataset.effect)):buttons,addEventListener:(n,f)=>events[n]=f};
 const ctx=vm.createContext({document,window:{addEventListener:(n,f)=>events[n==='blur'?'windowblur':n]=f},AbortController,performance:{now:()=>clock},
  setTimeout:(fn,ms)=>{const id=++timerId;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),
  fetch:(path,options)=>new Promise((resolve,reject)=>{const c={path,options,resolve,reject};pending.push(c);sent.push(c);})});
 vm.runInContext(script,ctx);
 const take=path=>{const i=pending.findIndex(c=>c.path===path);assert(i>=0,`missing ${path}`);return pending.splice(i,1)[0];};
 const respond=(c,body,ok=true)=>c.resolve({ok,json:async()=>body});
 const status=(seq=1,extra={})=>({result:'ok',request_sequence:seq,window:seq,move_remaining_ms:0,water_remaining_ms:0,
  move_cooldown_ms:0,water_cooldown_ms:0,move_last_duration_ms:600,water_last_duration_ms:1000,
  capabilities:{frenzy:true,move:true,water:true,move_and_water:true,bubbles:true,ignition:true,water_hold:true,bubbles_hold:true},drive_hold_id:0,drive_renewal:0,move_direction:'none',move_source:'none',water_source:'none',logical_outputs:{water:false},boot_held:false,state:'STOPPED',fault:'none',...extra});
 async function connect(){const c=take('/api/pair');assert.equal(c.options.body,'{}');respond(c,{result:'ok',token:'session'});await flush();respond(take('/api/state'),status());await flush();assert(!buttons[0].disabled);}
 async function start(){const promise=ctx.beginHold(buttons[0],1);await flush();respond(take('/api/state'),status(2));await flush();return {promise,call:take('/api/action')};}
 async function hold(){const {promise,call}=await start();respond(call,status(3,{result:'accepted',drive_hold_id:1,drive_renewal:1,move_remaining_ms:600,move_source:'web',state:'ACTIVE'}));await promise;}
 return {ctx,ids,buttons,events,document,pending,sent,timers,take,respond,status,connect,start,hold,advance:ms=>clock+=ms};
}
{
 const h=harness();await h.connect();const {promise,call}=await h.start();
 assert.deepEqual(JSON.parse(call.options.body),{sequence:1,window:2,operation:'drive_start',direction:'forward'});
 const stop=h.ctx.endHold();h.respond(h.take('/api/action'),h.status(4));await stop;
 h.respond(h.take('/api/state'),h.status(5));await flush();
 h.respond(call,h.status(3,{result:'accepted',drive_hold_id:1,drive_renewal:1,move_remaining_ms:600}));await promise;
 assert.equal(h.ids['move-time'].textContent,'');assert(![...h.timers.values()].some(t=>t.ms===150));
}
{
 const h=harness();await h.connect();const start=h.ctx.beginHold(h.buttons[0],1);await flush();const fresh=h.take('/api/state');
 const stop=h.ctx.endHold();await stop;
 h.respond(fresh,h.status(2));await start;
 assert(!h.sent.some(c=>JSON.parse(c.options.body).operation==='drive_start')); // Released before fresh window, never start.
}
{
 const h=harness();await h.connect();await h.hold();assert.equal(h.ids.water.disabled,false);
 // A second finger can start water while the first continues holding direction.
 const water=h.ctx.action();await flush();h.respond(h.take('/api/state'),h.status(4,{drive_hold_id:1,move_remaining_ms:600,move_source:'web'}));await flush();
 const wc=h.take('/api/action');assert.equal(JSON.parse(wc.options.body).operation,'water');
 assert.equal(h.buttons[0].disabled,false);
 h.respond(wc,h.status(5,{result:'accepted',drive_hold_id:1,drive_renewal:1,move_remaining_ms:600,water_remaining_ms:1000,move_source:'web',water_source:'web',logical_outputs:{water:true}}));await water;
 assert.equal(h.ids['move-time'].textContent,'按住行走');
 const stop=h.ctx.endHold();h.respond(h.take('/api/action'),h.status(6,{water_remaining_ms:800,water_source:'web',logical_outputs:{water:true}}));await stop;
 assert.equal(h.ids['water-time'].textContent,'0.8 s'); // Release leaves timed water running.
}
{
 const h=harness();await h.connect();h.ctx.render(h.status(2,{water_remaining_ms:5000,water_source:'web',logical_outputs:{water:true}}));
 assert.equal(h.buttons[0].disabled,false); // Already spraying does not disable movement.
 h.ctx.render(h.status(3,{move_remaining_ms:1000,move_source:'voice'}));assert.equal(h.buttons[0].disabled,false); // Can interrupt voice lane.
 const {promise,call}=await h.start();h.respond(call,h.status(6,{result:'voice_preempted',move_cooldown_ms:200}));await promise;
 assert.equal(h.ids.connection.textContent,'已连接');assert.equal(h.buttons[0].disabled,true);
 assert(![...h.timers.values()].some(t=>t.ms===150)); // No queued restart after cooldown.
}
{
 const h=harness();await h.connect();
 const p=h.ctx.poll();h.respond(h.take('/api/state'),h.status(2,{move_cooldown_ms:200,water_cooldown_ms:120}));await p;
 assert(h.buttons[0].disabled && h.ids.water.disabled);
 const entry=[...h.timers.entries()].find(([,t])=>t.ms===120);assert(entry);h.timers.delete(entry[0]);
 const next=entry[1].fn();h.respond(h.take('/api/state'),h.status(3,{move_cooldown_ms:80}));await next;
 assert(h.buttons[0].disabled && !h.ids.water.disabled);
 assert([...h.timers.values()].some(t=>t.ms===80));
}
{
 const h=harness();await h.connect();await h.hold();
 const entry=[...h.timers.entries()].find(([,t])=>t.ms===150);assert(entry);h.timers.delete(entry[0]);
 const renewal=entry[1].fn();const late=h.take('/api/action');
 const stop=h.ids.stop.events.click();h.respond(h.take('/api/stop'),h.status(5));await stop;
 h.respond(h.take('/api/state'),h.status(6));await flush();h.respond(late,h.status(4,{result:'renewed',drive_hold_id:1,drive_renewal:2,move_remaining_ms:600}));await renewal;
 assert.equal(h.ids['move-time'].textContent,'');assert(![...h.timers.values()].some(t=>t.ms===150));
}
for(const trigger of ['pointerup','pointercancel','lostpointercapture','pointermove','keyup','visibilitychange','offline','windowblur']){
 const h=harness();await h.connect();await h.hold();
 if(trigger==='visibilitychange'){h.document.hidden=true;h.events.visibilitychange();}
 else if(trigger==='offline'||trigger==='windowblur')h.events[trigger]();
 else if(trigger==='keyup') { // Keyboard-specific hold.
  h.ctx.clearHold();const p=h.ctx.beginHold(h.buttons[0]);await flush();h.respond(h.take('/api/state'),h.status(4));await flush();h.respond(h.take('/api/action'),h.status(5,{result:'accepted',drive_hold_id:2,drive_renewal:1,move_remaining_ms:600}));await p;
  h.buttons[0].events.keyup({key:' ',preventDefault(){}});
 } else h.buttons[0].events[trigger]({pointerId:1,clientX:101,clientY:50,preventDefault(){}});
 assert(h.pending.some(c=>c.path==='/api/release'||JSON.parse(c.options.body).operation==='drive_stop'),trigger);
 assert(![...h.timers.values()].some(t=>t.ms===150),trigger);
}
{
 const h=harness();await h.connect();await h.hold();h.document.hidden=true;h.events.visibilitychange();h.take('/api/release');
 assert(![...h.timers.values()].some(t=>t.ms===1500));h.document.hidden=false;h.events.visibilitychange();
 h.respond(h.take('/api/pair'),{result:'ok',token:'new-session'});await flush();h.respond(h.take('/api/state'),h.status(9));await flush();
 assert.equal(h.sent.filter(c=>JSON.parse(c.options.body).operation==='drive_start').length,1); // Foreground reconnect never resumes a hold.
}
{
 const h=harness();const late=h.take('/api/pair');h.document.hidden=true;h.events.visibilitychange();
 h.respond(late,{result:'ok',token:'late-session'});await flush();assert.equal(h.take('/api/release').options.headers['X-CyberTrack-Token'],'late-session');assert(h.ids.stop.disabled);
}
{
 const h=harness();await h.connect();const p=h.ctx.poll();h.take('/api/state').reject(new Error('network'));await p;
 assert(h.ids.stop.disabled);assert.equal(h.ids['move-time'].textContent,'—');assert([...h.timers.values()].some(t=>t.ms===1500));
 assert.equal(h.sent.filter(c=>c.path==='/api/action').length,0);
}
console.log('PASS: automatic connection, independent water/held movement, fresh start window, voice preemption cooldown, release/stop races, background/offline cancellation and reconnect without action replay');

{
 const h=harness();await h.connect();await h.hold();
 assert.equal(h.ids['hold-time'].textContent,'已按住 0.0 秒');
 h.advance(2340);const tick=[...h.timers.entries()].find(([,t])=>t.ms===100);assert(tick);h.timers.delete(tick[0]);tick[1].fn();
 assert.equal(h.ids['hold-time'].textContent,'已按住 2.3 秒');
 const stop=h.ctx.endHold();assert.equal(h.ids['hold-time'].textContent,'本次按住 2.3 秒');
 h.advance(5000);h.respond(h.take('/api/action'),h.status(4));await stop;
 assert.equal(h.ids['hold-time'].textContent,'本次按住 2.3 秒');
 assert(![...h.timers.values()].some(t=>t.ms===100));
}
for(const trigger of ['visibilitychange','offline','stop']){
 const h=harness();await h.connect();await h.hold();h.advance(1200);
 if(trigger==='stop')h.ids.stop.events.click();
 else if(trigger==='visibilitychange'){h.document.hidden=true;h.events.visibilitychange();}
 else h.events.offline();
 assert.equal(h.ids['hold-time'].textContent,'本次按住 1.2 秒');
 assert(![...h.timers.values()].some(t=>t.ms===100));
}
console.log('PASS: elapsed hold timer uses monotonic time, freezes at release despite delayed receipt, cancels on background/offline/global stop');

for (const kind of ['bubbles','ignition']) {
 const h=harness();await h.connect();await h.hold();
 // All four may be active. Starting a timed effect leaves held movement intact.
 h.ctx.render(h.status(4,{water_remaining_ms:10000,water_source:'web',bubbles_remaining_ms:kind==='ignition'?4000:0,
   bubbles_source:'web',ignition_remaining_ms:kind==='bubbles'?5000:0,ignition_source:'web',
   drive_hold_id:1,drive_renewal:1,move_remaining_ms:600,logical_outputs:{water:true,bubbles:kind==='ignition',ignition:kind==='bubbles'}}));
 assert(!h.ids[kind].disabled && !h.buttons[0].disabled);
 const effect=h.ctx.action(kind,5000);await flush();h.respond(h.take('/api/state'),h.status(5,{drive_hold_id:1,move_remaining_ms:600}));await flush();
 const call=h.take('/api/action');assert.equal(JSON.parse(call.options.body).operation,kind);assert.equal(JSON.parse(call.options.body).duration_ms,5000);
 h.respond(call,h.status(6,{result:'accepted',drive_hold_id:1,drive_renewal:1,move_remaining_ms:600,water_remaining_ms:10000,
   bubbles_remaining_ms:4000,ignition_remaining_ms:5000,move_source:'web',water_source:'web',bubbles_source:'web',ignition_source:'web',
   logical_outputs:{water:true,bubbles:true,ignition:true}}));await effect;
 assert.equal(h.ids['bubbles-label'].textContent,'吹泡泡中');assert.equal(h.ids['ignition-label'].textContent,'点火中');
 assert(h.ids.bubbles.disabled && h.ids.ignition.disabled);assert(!h.buttons[0].disabled);
 const stop=h.ctx.endHold();h.respond(h.take('/api/action'),h.status(7,{bubbles_remaining_ms:3500,ignition_remaining_ms:4500,logical_outputs:{bubbles:true,ignition:true}}));await stop;
 assert.equal(h.ids['bubbles-time'].textContent,'3.5 s');assert.equal(h.ids['ignition-time'].textContent,'4.5 s');
}
for (const kind of ['bubbles','ignition']) {
 const h=harness();await h.connect();const effect=h.ctx.action(kind);await flush();const fresh=h.take('/api/state');
 const stop=h.ids.stop.events.click();h.respond(h.take('/api/stop'),h.status(4));await stop;
 h.respond(fresh,h.status(2));await effect;
 assert(!h.sent.some(c=>c.path==='/api/action')); // Stop while acquiring a window cannot send delayed ignition.
 h.respond(h.take('/api/state'),h.status(5));await flush();assert(!h.ids[kind].disabled);
}
{
 const h=harness();await h.connect();
 h.ctx.render(h.status(2,{ignition_cooldown_ms:3000,bubbles_cooldown_ms:200}));
 assert(h.ids.ignition.disabled && h.ids.bubbles.disabled && !h.ids.water.disabled && !h.buttons[0].disabled);
 h.ctx.render(h.status(3,{ignition_cooldown_ms:2800}));assert(h.ids.ignition.disabled && !h.ids.bubbles.disabled);
}
console.log('PASS: bubbles/ignition controls, four-lane concurrent display, independent intervals, held-motion continuity and global-stop versus pending effect race');

{
 const h=harness();await h.connect();
 h.ctx.render(h.status(2,{capabilities:{frenzy:true,move:true,water:true,bubbles:false}}));
 assert(h.ids.bubbles.disabled && h.ids.ignition.disabled && !h.ids.water.disabled);
}
console.log('PASS: new effect controls require explicit firmware capabilities');

for(const kind of ['water','bubbles']) for(const seconds of [1,3,5,10,30]) {
 const h=harness();await h.connect();
 const b=h.ids[seconds===1?kind:kind+'-'+seconds];assert(!b.disabled);
 const action=b.events.click();await flush();h.respond(h.take('/api/state'),h.status(2));await flush();
 const call=h.take('/api/action');assert.equal(JSON.parse(call.options.body).duration_ms,seconds*1000);
 assert.equal(JSON.parse(call.options.body).operation,kind);
 h.respond(call,h.status(3,{result:'accepted',[kind+'_remaining_ms']:seconds*1000,[kind+'_source']:'web'}));await action;
 assert([1,3,5,10,30].every(s=>h.ids[s===1?kind:kind+'-'+s].disabled));
 assert(h.ids[kind+'-hold'].disabled);
 h.respond(h.take('/api/state'),h.status(4));await flush();
}
async function effectHold(h,kind,id=1,seq=2,pointer=2) {
 const p=h.ctx.beginHold(h.ids[kind+'-hold'],pointer);await flush();
 h.respond(h.take('/api/state'),h.status(seq));await flush();
 const call=h.take('/api/action');assert.deepEqual(JSON.parse(call.options.body),{operation:kind+'_start',sequence:id,window:seq});
 h.respond(call,h.status(seq+1,{result:'accepted',[kind+'_hold_id']:id,[kind+'_renewal']:1,[kind+'_remaining_ms']:600,[kind+'_source']:'web'}));await p;
}
for(const kind of ['water','bubbles']) {
 const h=harness();await h.connect();await effectHold(h,kind);
 assert.equal(h.ids[kind+'-time'].textContent,'按住'+(kind==='water'?'喷水':'吹泡泡'));
 const timer=[...h.timers.entries()].find(([,t])=>t.ms===150);assert(timer);h.timers.delete(timer[0]);
 const renew=timer[1].fn();const call=h.take('/api/action');assert.equal(JSON.parse(call.options.body).operation,kind+'_renew');
 h.respond(call,h.status(4,{result:'renewed',[kind+'_hold_id']:1,[kind+'_renewal']:2,[kind+'_remaining_ms']:600}));await renew;
 h.advance(1234);const stop=h.ctx.endHold(kind);assert.equal(h.ids[kind+'-hold-time'].textContent,'本次按住 1.2 秒');
 const sc=h.take('/api/action');assert.deepEqual(JSON.parse(sc.options.body),{operation:kind+'_stop',hold_id:1});
 h.respond(sc,h.status(5));await stop;assert(![...h.timers.values()].some(t=>t.ms===150));
}
{
 const h=harness();await h.connect();await h.hold();
 // Two additional fingers can begin together; start window transactions serialize.
 const water=h.ctx.beginHold(h.ids['water-hold'],2),bubbles=h.ctx.beginHold(h.ids['bubbles-hold'],3);
 await flush();h.respond(h.take('/api/state'),h.status(4,{drive_hold_id:1,move_remaining_ms:600}));await flush();
 const wc=h.take('/api/action');assert.equal(JSON.parse(wc.options.body).sequence,2);
 h.respond(wc,h.status(5,{result:'accepted',water_hold_id:2,water_renewal:1,water_remaining_ms:600,drive_hold_id:1,move_remaining_ms:600}));await water;await flush();
 h.respond(h.take('/api/state'),h.status(6,{water_hold_id:2,water_remaining_ms:600,drive_hold_id:1,move_remaining_ms:600}));await flush();
 const bc=h.take('/api/action');assert.equal(JSON.parse(bc.options.body).sequence,3);
 h.respond(bc,h.status(7,{result:'accepted',bubbles_hold_id:3,bubbles_renewal:1,bubbles_remaining_ms:600,water_hold_id:2,water_remaining_ms:600,drive_hold_id:1,move_remaining_ms:600}));await bubbles;
 assert.equal([...h.timers.values()].filter(t=>t.ms===150).length,3);
 // Moving focus between touch buttons must not release a still-held finger.
 h.buttons[0].events.blur();h.ids['water-hold'].events.blur();assert.equal(h.pending.length,0);
 const stop=h.ctx.endHold('water');const sc=h.take('/api/action');assert.equal(JSON.parse(sc.options.body).operation,'water_stop');
 h.respond(sc,h.status(8,{bubbles_hold_id:3,bubbles_remaining_ms:600,drive_hold_id:1,move_remaining_ms:600}));await stop;
 assert.equal([...h.timers.values()].filter(t=>t.ms===150).length,2);
 const all=h.ids.stop.events.click();h.respond(h.take('/api/stop'),h.status(9));await all;
 assert(![...h.timers.values()].some(t=>t.ms===150||t.ms===100));
}
for(const kind of ['water','bubbles']) for(const trigger of ['pointerup','pointercancel','lostpointercapture','pointermove','keyboardblur','visibilitychange','offline','windowblur']) {
 const h=harness();await h.connect();await effectHold(h,kind,1,2,trigger==='keyboardblur'?null:2);
 const b=h.ids[kind+'-hold'];
 if(trigger==='visibilitychange'){h.document.hidden=true;h.events.visibilitychange();}
 else if(trigger==='offline'||trigger==='windowblur')h.events[trigger]();
 else if(trigger==='keyboardblur')b.events.blur();
 else b.events[trigger]({pointerId:2,clientX:101,clientY:50,preventDefault(){}});
 assert(h.pending.some(c=>c.path==='/api/release'||JSON.parse(c.options.body).operation===kind+'_stop'),kind+trigger);
 assert(![...h.timers.values()].some(t=>t.ms===150));
}
for(const kind of ['water','bubbles']) {
 const h=harness();await h.connect();const p=h.ctx.beginHold(h.ids[kind+'-hold'],2);await flush();
 h.respond(h.take('/api/state'),h.status(2));await flush();const late=h.take('/api/action');
 const stop=h.ctx.endHold(kind);h.respond(h.take('/api/action'),h.status(4));await stop;
 h.respond(late,h.status(3,{result:'accepted',[kind+'_hold_id']:1,[kind+'_renewal']:1,[kind+'_remaining_ms']:600}));await p;
 assert(![...h.timers.values()].some(t=>t.ms===150)); // Late start receipt never renews a released hold.
}
{
 const h=harness();await h.connect();h.ctx.render(h.status(2,{capabilities:{frenzy:true,move:true,water:true,bubbles:true,ignition:true}}));
 assert(h.ids['water-hold'].disabled&&h.ids['bubbles-hold'].disabled&&!h.ids.water.disabled&&!h.ids.bubbles.disabled);
}
console.log('PASS: five one-tap durations per lane, independent held water/bubbles, three simultaneous holds, serialized starts, per-lane release, multitouch focus, cancel/offline/stop, late receipts and capability gating');

for(const seconds of [1,3,5]) {
 const h=harness();await h.connect();
 const action=h.ids[seconds===1?'ignition':'ignition-'+seconds].events.click();
 await flush();h.respond(h.take('/api/state'),h.status(2));await flush();
 const call=h.take('/api/action');assert.deepEqual(JSON.parse(call.options.body),{sequence:1,window:2,operation:'ignition',duration_ms:seconds*1000});
 h.respond(call,h.status(3,{result:'accepted',ignition_remaining_ms:seconds*1000,ignition_source:'web'}));await action;
 assert([1,3,5].every(s=>h.ids[s===1?'ignition':'ignition-'+s].disabled));
 h.respond(h.take('/api/state'),h.status(4,{ignition_cooldown_ms:3000}));await flush();
 assert([1,3,5].every(s=>h.ids[s===1?'ignition':'ignition-'+s].disabled));
 h.ctx.render(h.status(5));assert([1,3,5].every(s=>!h.ids[s===1?'ignition':'ignition-'+s].disabled));
}
assert(!html.includes('ignition-duration') && !html.includes('ignition-hold'));
console.log('PASS: ignition 1/3/5-second buttons map to exact durations, all disabled while active/cooling; no hold or dropdown');

for (const seconds of [5,10,30]) {
 const h=harness();await h.connect();assert(!h.ids['frenzy-'+seconds].disabled);
 const start=h.ids['frenzy-'+seconds].events.click();await flush();
 h.respond(h.take('/api/state'),h.status(2));await flush();
 const call=h.take('/api/action');assert.deepEqual(JSON.parse(call.options.body),{sequence:1,window:2,operation:'frenzy',duration_ms:seconds*1000});
 h.respond(call,h.status(3,{result:'accepted',frenzy_remaining_ms:seconds*1000}));await start;await flush();
 assert.equal(h.ids['frenzy-time'].textContent,'剩余 '+seconds.toFixed(1)+' 秒');
 assert(h.ids['frenzy-5'].disabled && h.ids.water.disabled && h.ids['ignition-3'].disabled && h.buttons[0].disabled);
 assert(!h.ids.stop.disabled);
 h.events.windowblur();assert(h.sent.some(c=>c.path==='/api/release'));
}
{
 const h=harness();await h.connect();h.ctx.render(h.status(2,{capabilities:{water:true}}));
 assert(h.ids['frenzy-5'].disabled);
 await h.ctx.action('frenzy',5000);assert(!h.sent.some(c=>c.path==='/api/action'));
}
console.log('PASS: frenzy 5/10/30-second payloads, countdown, capability gating and blur release');

for(const [kind,label] of [['water','喷水'],['bubbles','吹泡泡'],['ignition','点火'],['frenzy','狂暴模式']]) {
 const h=harness();await h.connect();const start=h.ctx.action(kind,5000);await flush();
 h.respond(h.take('/api/state'),h.status(2));await flush();
 h.respond(h.take('/api/action'),h.status(3,{result:'accepted',[kind+'_remaining_ms']:5000}));await start;
 assert.equal(h.ids.message.textContent,'正在'+label+'。');
 // Completion comes from the device, not a local timeout; cooling is no longer running.
 h.respond(h.take('/api/state'),h.status(4,{[kind+'_cooldown_ms']:1000}));await flush();
 assert.equal(h.ids.message.textContent,'动作已结束。');
 h.ctx.render(h.status(3,{[kind+'_remaining_ms']:4000}));
 assert.equal(h.ids.message.textContent,'动作已结束。'); // stale running state cannot restore the banner
}
{
 const h=harness();await h.connect();const start=h.ctx.action('water',1000);await flush();
 h.respond(h.take('/api/state'),h.status(2));await flush();
 h.respond(h.take('/api/action'),h.status(3,{result:'accepted',water_remaining_ms:1000,bubbles_remaining_ms:3000}));await start;
 assert.equal(h.ids.message.textContent,'正在喷水、吹泡泡。');
 h.respond(h.take('/api/state'),h.status(4,{bubbles_remaining_ms:2000}));await flush();
 assert.equal(h.ids.message.textContent,'正在吹泡泡。');
 h.ctx.render(h.status(5));assert.equal(h.ids.message.textContent,'动作已结束。');
}
{
 const h=harness();await h.connect();h.ctx.activityMessage(h.status(2,{frenzy_remaining_ms:4000,ignition_remaining_ms:0}));
 h.ctx.render(h.status(3,{frenzy_remaining_ms:3000,ignition_remaining_ms:0}));
 assert.equal(h.ids.message.textContent,'正在狂暴模式。'); // ignition OFF phase does not finish the mode
 h.ctx.render(h.status(4,{state:'FAULT'}));assert.equal(h.ids.message.className,'error');
 h.ctx.render(h.status(5));assert.equal(h.ids.message.textContent,'设备故障，动作已停止。');
 h.ctx.message('全部停止。');h.ctx.render(h.status(6));assert.equal(h.ids.message.textContent,'全部停止。');
 h.ctx.message('请求被拒绝。',true);h.ctx.render(h.status(7));assert.equal(h.ids.message.textContent,'请求被拒绝。');
}
{
 const h=harness();await h.connect();const start=h.ctx.action('water',1);await flush();
 h.respond(h.take('/api/state'),h.status(2));await flush();const late=h.take('/api/action');
 h.ctx.render(h.status(5)); // newer state arrives before the accepted response
 h.respond(late,h.status(3,{result:'accepted',water_remaining_ms:1}));await start;
 assert.equal(h.ids.message.textContent,'动作已结束。');
}
console.log('PASS: live action notices finish on device state, retain concurrent activity, ignore stale receipts and preserve stop/error messages');

{
 const h=harness();await h.connect();
 h.ctx.render(h.status(2,{sequence_active:true,sequence_step:1,sequence_steps:3,sequence_result:'running'}));
 assert.equal(h.ids.message.textContent,'动作序列 1/3：执行中。');
 h.ctx.render(h.status(3,{sequence_active:true,sequence_step:1,sequence_steps:3,sequence_result:'waiting'}));
 assert.equal(h.ids.message.textContent,'动作序列 1/3：等待下一步。');
 h.ctx.render(h.status(4,{sequence_active:false,sequence_result:'cancelled'}));
 assert.equal(h.ids.message.textContent,'动作序列已取消。');
 h.ctx.activityMessage(h.status(5,{sequence_result:'cancelled',water_remaining_ms:1000}));
 assert.equal(h.ids.message.textContent,'正在喷水。');
}
console.log('PASS: sequence running/waiting/cancelled status never misreports inter-step waiting as completion');
