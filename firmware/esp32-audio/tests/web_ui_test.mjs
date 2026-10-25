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
 const document={hidden:false,getElementById:id=>ids[id],querySelectorAll:()=>buttons,addEventListener:(n,f)=>events[n]=f};
 const ctx=vm.createContext({document,window:{addEventListener:(n,f)=>events[n==='blur'?'windowblur':n]=f},AbortController,performance:{now:()=>clock},
  setTimeout:(fn,ms)=>{const id=++timerId;timers.set(id,{fn,ms});return id;},clearTimeout:id=>timers.delete(id),
  fetch:(path,options)=>new Promise((resolve,reject)=>{const c={path,options,resolve,reject};pending.push(c);sent.push(c);})});
 vm.runInContext(script,ctx);
 const take=path=>{const i=pending.findIndex(c=>c.path===path);assert(i>=0,`missing ${path}`);return pending.splice(i,1)[0];};
 const respond=(c,body,ok=true)=>c.resolve({ok,json:async()=>body});
 const status=(seq=1,extra={})=>({result:'ok',request_sequence:seq,window:seq,move_remaining_ms:0,water_remaining_ms:0,
  move_cooldown_ms:0,water_cooldown_ms:0,move_last_duration_ms:600,water_last_duration_ms:1000,
  drive_hold_id:0,drive_renewal:0,move_direction:'none',move_source:'none',water_source:'none',logical_outputs:{water:false},boot_held:false,state:'STOPPED',fault:'none',...extra});
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
 const stop=h.ctx.endHold();h.respond(h.take('/api/action'),h.status(3));await stop;
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
for(const trigger of ['pointerup','pointercancel','lostpointercapture','pointermove','blur','keyup','visibilitychange','offline','windowblur']){
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
