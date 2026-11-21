// Execute the shipped page script with a fake DOM/transport, without hardware.
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import vm from 'node:vm';
const html=readFileSync(new URL('../web/index.html',import.meta.url),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
const flush=()=>new Promise(r=>setImmediate(r));
function rangeStatus(h, seq, distance = {}, extra = {}) {
 return h.status(seq, {capabilities:{distance:true}, distance:{valid:true,error:'none',distance_mm:1000,age_ms:30,...distance},...extra});
}
assert(!html.includes('id="distance-state"'));
assert(!/theatre|show_draft|show_edit|show_confirm|show-presets/.test(html));
assert(!html.includes('id="pairing"') && !html.includes('id="combined"') && !html.includes('id="release"'));
function harness(){
 const element=()=>({value:'1000',disabled:true,style:{},events:{},classList:{toggle(){}},attributes:{},setAttribute(k,v){this.attributes[k]=v;},captured:false,
  setPointerCapture(){this.captured=true;},hasPointerCapture(){return this.captured;},releasePointerCapture(){this.captured=false;},
  getBoundingClientRect(){return {left:0,top:0,right:100,bottom:100};},addEventListener(n,f){this.events[n]=f;}});
 const ids=Object.fromEntries([...html.matchAll(/id="([^"]+)"/g)].map(m=>[m[1],element()]));
 const buttons=['forward','backward','left','right'].map(direction=>({...element(),dataset:{direction}}));
 const events={},pending=[],sent=[],timers=new Map();let timerId=0, clock=0;
 for(const kind of ['water','bubbles']) ids[kind+'-hold'].dataset={hold:kind};
 const effectButtons=[];
 for(const kind of ['water','bubbles']) for(const sec of [1,3,5,10,30]) {
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
  capabilities:{move:true,water:true,move_and_water:true,bubbles:true,water_hold:true,bubbles_hold:true},drive_hold_id:0,drive_renewal:0,move_direction:'none',move_source:'none',water_source:'none',logical_outputs:{water:false},boot_held:false,state:'STOPPED',fault:'none',...extra});
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
 assert.equal(h.ids['move-time'].textContent,'');
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
 const h=harness(); await h.connect();
 h.ctx.render(rangeStatus(h,2));
 assert.equal(h.ids['distance-value'].textContent,'100 cm');
 const expiry=[...h.timers.values()].find(t=>t.ms===471);assert(expiry);expiry.fn();
 assert.equal(h.ids['distance-value'].textContent,'-');
 h.ctx.render(rangeStatus(h,3));
 h.ctx.render(rangeStatus(h,2,{distance_mm:2500})); // Old response cannot replace newer data.
 assert.equal(h.ids['distance-value'].textContent,'100 cm');
 h.ctx.disconnect('offline');
 assert.equal(h.ids['distance-value'].textContent,'-');
 assert.equal(h.sent.filter(c=>c.path==='/api/action').length,0);
}
for(const distance of [
 {valid:false,error:'no_echo',distance_mm:null}, {valid:false,error:'echo_high'},
 {valid:false,error:'invalid_echo'}, {valid:false,error:'driver_error'},
 {valid:false,error:'out_of_range'}, {valid:false,error:'not_ready'},
 {error:'stale'}, {age_ms:501}, {age_ms:-1}, {age_ms:null},
 {distance_mm:null}, {distance_mm:19}, {distance_mm:4001}, {distance_mm:'1000'},
]){
 const h=harness(); await h.connect(); h.ctx.render(rangeStatus(h,2));
 h.ctx.render(rangeStatus(h,3,distance));
 assert.equal(h.ids['distance-value'].textContent,'-',JSON.stringify(distance));
 assert.equal(h.sent.filter(c=>c.path==='/api/action').length,0);
}
{
 const h=harness(); await h.connect(); h.ctx.render(rangeStatus(h,2));
 h.ctx.render(h.status(3)); // Connected old firmware has no distance capability.
 assert.equal(h.ids['distance-value'].textContent,'-');
 const pending=h.ctx.poll();const request=h.take('/api/state');h.advance(600);
 h.respond(request,rangeStatus(h,4));await pending;
 assert.equal(h.ids['distance-value'].textContent,'-'); // Network latency counts toward age.
}
console.log('PASS: distance display, units, local expiry, delayed/out-of-order responses, errors, old firmware and offline invalidation; no movement requests');

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

for (const kind of ['bubbles']) {
 const h=harness();await h.connect();await h.hold();
 // All four may be active. Starting a timed effect leaves held movement intact.
 h.ctx.render(h.status(4,{water_remaining_ms:10000,water_source:'web',bubbles_remaining_ms:0,
   bubbles_source:'web',
   drive_hold_id:1,drive_renewal:1,move_remaining_ms:600,logical_outputs:{water:true,bubbles:false}}));
 assert(!h.ids[kind].disabled && !h.buttons[0].disabled);
 const effect=h.ctx.action(kind,5000);await flush();h.respond(h.take('/api/state'),h.status(5,{drive_hold_id:1,move_remaining_ms:600}));await flush();
 const call=h.take('/api/action');assert.equal(JSON.parse(call.options.body).operation,kind);assert.equal(JSON.parse(call.options.body).duration_ms,5000);
 h.respond(call,h.status(6,{result:'accepted',drive_hold_id:1,drive_renewal:1,move_remaining_ms:600,water_remaining_ms:10000,
   bubbles_remaining_ms:4000,move_source:'web',water_source:'web',bubbles_source:'web',
   logical_outputs:{water:true,bubbles:true}}));await effect;
 assert.equal(h.ids['bubbles-time'].textContent,'4.0 s');
 assert(h.ids.bubbles.disabled);assert(!h.buttons[0].disabled);
 const stop=h.ctx.endHold();h.respond(h.take('/api/action'),h.status(7,{bubbles_remaining_ms:3500,logical_outputs:{bubbles:true}}));await stop;
 assert.equal(h.ids['bubbles-time'].textContent,'3.5 s');
}
assert(!/ignition|frenzy/i.test(html));
for (const kind of ['ignition', 'frenzy']) {
 const h=harness();await h.connect();
 await h.ctx.action(kind,1000);
 assert(!h.sent.some(c=>c.path==='/api/action'));
}
for(const [kind,label] of [['water','喷水'],['bubbles','吹泡泡']]) {
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

{ // A slider input during a hold changes only speed, not hold ownership or duration.
 const h=harness();await h.connect();await h.hold();
 h.ctx.render(h.status(4,{capabilities:{speed_control:true},web_speed_percent:100,drive_hold_id:1,drive_renewal:1,move_remaining_ms:500,move_source:'web'}));
 h.ids['move-speed'].value='60';const run=h.ids['move-speed'].events.input();await flush();
 h.respond(h.take('/api/state'),h.status(5,{capabilities:{speed_control:true},web_speed_percent:100,drive_hold_id:1,move_remaining_ms:450}));await flush();
 const c=h.take('/api/action');assert.deepEqual(JSON.parse(c.options.body),{operation:'set_speed',sequence:2,window:5,speed_percent:60});
 h.respond(c,h.status(6,{capabilities:{speed_control:true},web_speed_percent:60,move_speed_percent:60,move_direction:'forward',drive_hold_id:1,move_remaining_ms:400}));await run;
 assert.equal(h.ids['speed-value'].textContent,'60%');assert.equal(h.ids['move-state'].textContent,'前进');assert.equal(h.ids['drive-speed'].textContent,'60%');
 assert.equal(h.sent.filter(x=>x.path==='/api/action').length,2);assert(!h.sent.some(x=>x.path==='/api/stop'));
}
{ // Rapid input sends only the latest desired value after each in-flight receipt.
 const h=harness();await h.connect();h.ctx.render(h.status(2,{capabilities:{speed_control:true},web_speed_percent:100}));
 h.ids['move-speed'].value='80';const run=h.ids['move-speed'].events.input();await flush();
 h.respond(h.take('/api/state'),h.status(3,{capabilities:{speed_control:true}}));await flush();const first=h.take('/api/action');
 h.ids['move-speed'].value='60';await h.ids['move-speed'].events.input();h.ids['move-speed'].value='70';await h.ids['move-speed'].events.input();
 h.respond(first,h.status(4,{capabilities:{speed_control:true},web_speed_percent:80}));await flush();
 assert.equal(h.ids['speed-value'].textContent,'70%');
 h.respond(h.take('/api/state'),h.status(5,{capabilities:{speed_control:true},web_speed_percent:80}));await flush();
 const last=h.take('/api/action');assert.equal(JSON.parse(last.options.body).speed_percent,70);
 h.respond(last,h.status(6,{capabilities:{speed_control:true},web_speed_percent:70}));await run;
 assert.equal(h.sent.filter(x=>x.path==='/api/action').length,2);assert.equal(h.ids['speed-value'].textContent,'70%');
}
{ // Stop invalidates an in-flight freshness check; no delayed speed update.
 const h=harness();await h.connect();h.ctx.render(h.status(2,{capabilities:{speed_control:true},web_speed_percent:100}));
 h.ids['move-speed'].value='60';const run=h.ids['move-speed'].events.input();await flush();const fresh=h.take('/api/state');
 const stop=h.ids.stop.events.click();h.respond(h.take('/api/stop'),h.status(4,{capabilities:{speed_control:true},web_speed_percent:100}));await stop;
 h.respond(fresh,h.status(3,{capabilities:{speed_control:true}}));await run;
 assert(!h.sent.some(x=>x.path==='/api/action'));assert.equal(h.ids['speed-value'].textContent,'100%');
}
{
 const h=harness();await h.connect();assert(h.ids['move-speed'].disabled);
 h.ids['move-speed'].value='60';await h.ids['move-speed'].events.input();assert(!h.sent.some(x=>x.path==='/api/action'));
}
console.log('PASS: live speed slider, latest-value coalescing, source status, capability gate and stop races without action replay');

{ // Even synthetic stale clients cannot submit a below-floor setting.
 const h=harness();await h.connect();h.ctx.render(h.status(2,{capabilities:{speed_control:true},web_speed_percent:100}));
 h.ids['move-speed'].value='59';await h.ids['move-speed'].events.input();assert(!h.sent.some(x=>x.path==='/api/action'));
}

{
 const h=harness();await h.connect();
 let prevented=false;h.events.selectstart({preventDefault(){prevented=true;}});assert(prevented);
 h.ctx.render(rangeStatus(h,2));
 h.advance(100);h.ctx.render(rangeStatus(h,3,{distance_mm:1010}));
 assert.equal(h.ids['distance-value'].textContent,'100 cm');
 h.advance(100);h.ctx.render(rangeStatus(h,4,{distance_mm:1030}));
 assert.equal(h.ids['distance-value'].textContent,'100 cm');
 h.advance(160);h.ctx.render(rangeStatus(h,5,{distance_mm:1040}));
 assert.equal(h.ids['distance-value'].textContent,'104 cm');
 h.advance(20);h.ctx.render(rangeStatus(h,6,{distance_mm:300}));
 assert.equal(h.ids['distance-value'].textContent,'30 cm'); // Approaching target is not slowly averaged.
 h.ctx.render(rangeStatus(h,7,{valid:false,error:'no_echo',distance_mm:null}));
 assert.equal(h.ids['distance-value'].textContent,'-');
 h.ctx.render(rangeStatus(h,8,{distance_mm:310}));
 assert.equal(h.ids['distance-value'].textContent,'31 cm'); // Reset hysteresis after invalid sample.
 const run=h.ctx.poll();h.respond(h.take('/api/state'),rangeStatus(h,9));await run;
 assert([...h.timers.values()].some(t=>t.ms===200));
 h.ctx.render(h.status(10,{move_speed_percent:100,move_direction:'left'}));
 assert.equal(h.ids['drive-speed'].textContent,'100%');
 h.ctx.render(h.status(11,{move_speed_percent:0}));assert.equal(h.ids['drive-speed'].textContent,'—');
 h.ctx.disconnect('offline');assert.equal(h.ids['drive-speed'].textContent,'—');
 assert.equal(h.sent.filter(c=>c.path==='/api/action').length,0);
}
console.log('PASS: range hysteresis, immediate large change/invalid clearing, 200 ms telemetry polling, separate speed and selection prevention');

{
 const h=harness();await h.connect();
 h.ctx.render(h.status(2,{move_remaining_ms:10000,move_direction:'forward',move_source:'voice',water_remaining_ms:1000,water_source:'web'}));
 assert.equal(h.ids['move-state'].textContent,'前进');assert.equal(h.ids['move-time'].textContent,'10.0 s');
 assert.equal(h.ids['water-state'].textContent,'');assert.equal(h.ids['water-time'].textContent,'1.0 s');
 h.ctx.render(h.status(3,{move_remaining_ms:2147483647,move_direction:'left'}));assert.equal(h.ids['move-time'].textContent,'597 h');
 h.ctx.render(h.status(4,{water_hold_id:1,water_remaining_ms:600}));assert.equal(h.ids['water-time'].textContent,'持续');
 h.ctx.render(h.status(5,{water_cooldown_ms:100}));assert.equal(h.ids['water-state'].textContent,'冷却');
 h.ctx.render(h.status(6,{state:'FAULT'}));assert.equal(h.ids['move-state'].textContent,'故障');
 h.ctx.disconnect('offline');assert.equal(h.ids['move-state'].textContent,'');assert.equal(h.ids['move-time'].textContent,'—');
}
console.log('PASS: compact channel states retain direction, countdown, hold, cooldown, fault and disconnected status');
{
 const h=harness();await h.connect();
 h.ctx.render(h.status(2,{proximity:{forward_blocked:true}}));
 assert(h.buttons[0].disabled); assert(h.buttons.slice(1).every(b=>!b.disabled));
 assert(!h.ids.water.disabled);
 h.ctx.render(h.status(3,{proximity:{forward_blocked:false}}));
 assert(!h.buttons[0].disabled);assert(!h.sent.some(c=>JSON.parse(c.options.body).operation==='drive_start'));
}
for(const blocked of [true,false]) {
 const h=harness();await h.connect();await h.hold();
 const renewal=[...h.timers.values()].find(t=>t.ms===150);assert(renewal);const wait=renewal.fn();
 h.respond(h.take('/api/action'),h.status(4,{result:'drive_cancelled',proximity:{forward_blocked:blocked},water_remaining_ms:2000,water_source:'web',logical_outputs:{water:true}}));
 await wait;await flush();
 assert(!h.sent.some(c=>['stop','release','drive_start'].includes(JSON.parse(c.options.body).operation) && c!==h.sent.find(x=>JSON.parse(x.options.body).operation==='drive_start')));
 assert.equal(h.ids.stop.disabled,false);
 assert.equal(h.buttons[0].disabled,blocked);
 assert(h.ids.message.textContent.includes(blocked?'前方过近':'行走已停止'));
}
console.log('PASS: proximity locks only forward, cancellation preserves connection/effects, recovery never restarts');

for (const enabled of [false,true]) {
 const h=harness();await h.connect();
 assert(h.ids['auto-avoidance'].disabled); // Older firmware cannot configure this preference.
 h.ctx.render(h.status(2,{proximity:{auto_avoidance_enabled:enabled,forward_blocked:false}}));
 const b=h.ids['auto-avoidance'];assert(!b.disabled);assert.equal(b.attributes['aria-checked'],String(enabled));
 const setting=b.events.click();await flush();
 assert(b.disabled);assert.equal(b.attributes['aria-checked'],String(enabled));
 h.respond(h.take('/api/state'),h.status(3,{proximity:{auto_avoidance_enabled:enabled}}));await flush();
 const call=h.take('/api/action');assert.deepEqual(JSON.parse(call.options.body),{operation:'set_auto_avoidance',sequence:1,window:3,enabled:!enabled});
 h.respond(call,h.status(4,{proximity:{auto_avoidance_enabled:!enabled,forward_blocked:!enabled}}));await setting;
 assert.equal(b.attributes['aria-checked'],String(!enabled));assert(!b.disabled);
 h.ctx.render(h.status(3,{proximity:{auto_avoidance_enabled:enabled}}));
 assert.equal(b.attributes['aria-checked'],String(!enabled)); // Late status cannot roll back the switch.
 h.ctx.disconnect('test');assert(b.disabled);assert.equal(b.textContent,'未连接');
 h.respond(h.take('/api/state'),h.status(5));await flush(); // Finish the old in-flight poll.
 const reconnect=h.ctx.connect();h.respond(h.take('/api/pair'),{result:'ok',token:'new'});await flush();
 h.respond(h.take('/api/state'),h.status(1,{proximity:{auto_avoidance_enabled:!enabled}}));await reconnect;
 assert.equal(b.attributes['aria-checked'],String(!enabled));
}
{
 const h=harness();await h.connect();
 h.ctx.render(h.status(2,{proximity:{auto_avoidance_enabled:false}}));
 const setting=h.ids['auto-avoidance'].events.click();await flush();
 h.respond(h.take('/api/state'),h.status(3,{proximity:{auto_avoidance_enabled:false}}));await flush();
 h.take('/api/action').reject(new Error('network'));await setting;
 assert(h.ids['auto-avoidance'].disabled);assert.equal(h.ids['auto-avoidance'].textContent,'未连接');
}
{
 const h=harness();await h.connect();
 h.ctx.render(h.status(2,{proximity:{auto_avoidance_enabled:false}}));
 const setting=h.ids['auto-avoidance'].events.click();await flush();
 h.respond(h.take('/api/state'),h.status(3,{proximity:{auto_avoidance_enabled:false}}));await flush();
 const call=h.take('/api/action');
 const stopping=h.ids.stop.events.click();h.respond(h.take('/api/stop'),h.status(5,{proximity:{auto_avoidance_enabled:true}}));await stopping;
 h.respond(call,h.status(4,{proximity:{auto_avoidance_enabled:false}}));await setting;
 assert.equal(h.ids['auto-avoidance'].attributes['aria-checked'],'true');
}
console.log('PASS: automatic avoidance switch uses device receipts, validates capability, ignores stale replies and handles failure/stop races');
{
 const h=harness();await h.connect();
 const before=h.sent.length;
 h.ids.help.events.toggle();assert.equal(h.sent.length,before);
 assert.match(h.ids.diagnosis.textContent,/没有可用的最近动作回执/);
 const recent={valid:true,operation:'move',result:'not_ready_or_busy',age_ms:300,source:'voice'};
 h.ctx.render(h.status(2,{recent_command:recent,move_cooldown_ms:100}));
 assert.match(h.ids.diagnosis.textContent,/间隔等待/);
 assert.match(h.ids.diagnosis.textContent,/回执未细分原因/);
 assert(!h.ids.diagnosis.textContent.includes('电池没电'));
 h.ctx.render(h.status(3,{recent_command:{...recent,result:'accepted'},move_remaining_ms:100}));
 assert.match(h.ids.diagnosis.textContent,/不等于实物动作完成/);
 h.advance(1501);h.ids.help.events.toggle();assert.match(h.ids.diagnosis.textContent,/没有新鲜/);
 assert.equal(h.sent.length,before);
 h.ctx.render(h.status(4,{boot_held:true,proximity:{forward_blocked:true},state:'FAULT',recent_command:{...recent,age_ms:null}}));
 assert.match(h.ids.diagnosis.textContent,/BOOT 正按下/);
 assert.match(h.ids.diagnosis.textContent,/前进受阻/);
 assert.match(h.ids.diagnosis.textContent,/没有可用/);
 h.ctx.render(h.status(3,{recent_command:recent}));assert.match(h.ids.diagnosis.textContent,/BOOT 正按下/);
 h.ctx.disconnect('offline');assert.match(h.ids.diagnosis.textContent,/没有新鲜/);
}
console.log('PASS: readonly explanation, evidence-specific reasons, recent receipt age, stale/unknown/offline/out-of-order handling; no action requests');

// Losing a hold-stop reply releases only web ownership. Keep local-stop guidance
// while pairing succeeds and until a fresh actionable state arrives.
{
 const h=harness();await h.connect();await h.hold();
 const end=h.ctx.endHold();h.take('/api/action').reject(new Error('offline'));await end;
 assert(h.pending.some(c=>c.path==='/api/release'));assert(!h.sent.some(c=>c.path==='/api/stop'));
 assert.match(h.ids.message.textContent,/无法确认.*BOOT/);
 const reconnect=h.ctx.connect();h.respond(h.take('/api/pair'),{result:'ok',token:'new'});await flush();
 assert.match(h.ids.message.textContent,/BOOT/);
 h.advance(1600);
 h.respond(h.take('/api/state'),h.status(9));await reconnect;
 assert.match(h.ids.message.textContent,/BOOT/);assert(h.buttons[0].disabled);
 const fresh=h.ctx.poll();
 h.respond(h.take('/api/state'),h.status(10,{state:'ACTIVE',bubbles_source:'voice',bubbles_remaining_ms:4800}));
 await fresh;assert.match(h.ids.message.textContent,/正在.*泡泡/);
 assert(!h.sent.slice(-2).some(c=>c.path==='/api/action'));
}
{
 const h=harness();await h.connect();h.events.offline();
 assert(!h.ids.message.textContent.includes('BOOT'));
}
console.log('PASS: unconfirmed hold-stop survives pairing until a fresh state; concurrent voice output stays visible');

// A timed effect may have started even if its response is lost.
for (const kind of ['water', 'bubbles']) {
 const h=harness();await h.connect();
 const action=h.ctx.action(kind);await flush();
 h.respond(h.take('/api/state'),h.status(2));await flush();
 h.take('/api/action').reject(new Error('offline'));await action;
 assert.match(h.ids.message.textContent,/无法确认.*BOOT/,kind);
 assert(h.pending.some(c=>c.path==='/api/release'),kind);
 assert(h.ids[kind].disabled,kind);
}
console.log('PASS: lost timed-effect replies preserve BOOT guidance and release the web session');
