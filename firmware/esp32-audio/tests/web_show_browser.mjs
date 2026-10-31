// Real Chromium DOM and input events; all transport is local, synthetic and intercepted.
import {pathToFileURL} from 'node:url';
import {readFile, mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.CYBERTRACK_PLAYWRIGHT_MODULE
 ? pathToFileURL(process.env.CYBERTRACK_PLAYWRIGHT_MODULE).href : 'playwright');
const html=await readFile('firmware/esp32-audio/web/index.html','utf8');
const step=(direction='none',move_ms=0,bubbles_ms=1000)=>({direction,move_ms,water_ms:0,bubbles_ms,ignition_ms:0,speed_percent:100});
await mkdir('output/improvements/show-browser',{recursive:true});
const browser=await chromium.launch({headless:true});
try {
 for(const [width,height] of [[390,844],[320,568],[1280,800]]) {
  const page=await browser.newPage({viewport:{width,height}}), errors=[], requests=[];
  let seq=0, revision=0, starts=0, draft=null, active=false, conflictNext=false, dropRelease=false;
  const setDraft=steps=>{draft={active:true,revision:++revision,steps:structuredClone(steps),expires_in_ms:300000,source:'voice'};};
  async function loadDeviceDraft(steps) {
   setDraft(steps);
   await page.waitForFunction(expected=>deviceShow()?.revision===expected, revision);
   await page.locator('#show-load').click();
  }
  const status=(result='ok')=>({result,request_sequence:++seq,window:seq,state:active?'ACTIVE':'STOPPED',fault:'none',boot_held:false,
   capabilities:{show_draft:true,move:true,bubbles:true,speed_control:true},
   move_remaining_ms:0,water_remaining_ms:0,bubbles_remaining_ms:active?1000:0,ignition_remaining_ms:0,
   move_cooldown_ms:0,water_cooldown_ms:0,bubbles_cooldown_ms:0,ignition_cooldown_ms:0,
   sequence_active:active,sequence_source:active?'web':'none',sequence_step:active?1:0,sequence_steps:active?2:0,
   sequence_result:active?'running':'none',show_draft:structuredClone(draft)||{active:false,revision:0,steps:[],expires_in_ms:0},
   proximity:{forward_blocked:false,auto_avoidance_enabled:false}});
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/')return route.fulfill({contentType:'text/html',body:html});
   const body=JSON.parse(route.request().postData()||'{}');requests.push({path,body});
   if(path==='/api/pair')return route.fulfill({json:{result:'ok',token:'local-test-only'}});
   if(path==='/api/state') {
    if(conflictNext){conflictNext=false;setDraft([step('none',0,3000)]);}
    return route.fulfill({json:status()});
   }
   if(path==='/api/release' && dropRelease)return route.abort();
   if(path==='/api/stop'||path==='/api/release'){active=false;draft=null;return route.fulfill({json:status()});}
   if(path!=='/api/action')return route.abort();
   if(body.operation==='show_edit'){
    const edit=body.draft;
    if(edit.revision!==(draft?.revision||0))return route.fulfill({json:status('draft_changed')});
    if(edit.edit==='cancel'){draft=null;return route.fulfill({json:status('draft_cancelled')});}
    const steps=draft?structuredClone(draft.steps):[];
    if(edit.edit==='replace')setDraft(JSON.parse(edit.steps_json));
    else if(edit.edit==='replace_step'){steps[edit.step-1]=JSON.parse(edit.steps_json)[0];setDraft(steps);}
    else if(edit.edit==='remove_step'){steps.splice(edit.step-1,1);setDraft(steps);}
    else throw Error('unexpected edit');
    return route.fulfill({json:status('draft_saved')});
   }
   assert.equal(body.operation,'show_confirm');
   if(!draft || body.revision!==draft.revision)return route.fulfill({json:status('draft_changed')});
   draft=null;active=true;starts++;return route.fulfill({json:status('accepted')});
  });
  await page.goto('http://cybertrack.test/');
  await page.locator('#connection').filter({hasText:'已连接'}).waitFor();
  await page.locator('#theatre summary').click();
  for(const name of ['entry','celebrate','curtain'])await page.locator('#show-'+name).click();
  assert.equal(requests.filter(r=>r.path==='/api/action').length,0);
  await page.locator('#show-entry').click();
  await page.locator('#show-save').click();
  await page.locator('#show-notice').filter({hasText:'预览设备草稿 v1'}).waitFor();
  assert(await page.locator('#show-confirm').isDisabled());
  await page.locator('#show-reviewed').check();assert(await page.locator('#show-confirm').isEnabled());
  await page.locator('#show-step').fill('2');await page.locator('#show-step').press('Tab');
  await page.locator('#show-bubbles').fill('2');
  assert(await page.locator('#show-confirm').isDisabled());assert(await page.locator('#show-save').isDisabled());
  await page.locator('#show-apply').click();await page.locator('#show-save').click();
  await page.locator('#show-notice').filter({hasText:'预览设备草稿 v2'}).waitFor();
  assert.deepEqual(draft.steps,[step('forward',600,0),step('none',0,2000)]);
  const edits=requests.filter(r=>r.body.operation==='show_edit');assert.equal(edits.at(-1).body.draft.edit,'replace_step');
  assert.equal(starts,0);assert(await page.locator('#show-confirm').isDisabled());
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.locator('#show-preview').scrollIntoViewIfNeeded();
  await page.screenshot({path:`output/improvements/show-browser/${width}-editor.png`});
  await page.locator('#show-reviewed').check();
  await page.locator('#show-confirm').scrollIntoViewIfNeeded();
  const confirmBox=await page.locator('#show-confirm').boundingBox(),dock=await page.locator('.stop-bar').boundingBox();
  assert(confirmBox.y+confirmBox.height<=dock.y);
  await page.screenshot({path:`output/improvements/show-browser/${width}-confirm.png`});
  await page.locator('#show-confirm').click();
  await page.locator('#show-notice').filter({hasText:'表演请求已接受'}).waitFor();
  assert.equal(starts,1);assert(await page.locator('#show-confirm').isDisabled());
  await page.locator('#stop').click();
  await page.locator('#message').filter({hasText:'全部停止'}).waitFor();
  await loadDeviceDraft([step('backward',2000,1000)]);
  const preview=page.locator('#show-preview');
  assert.match(await preview.innerText(),/同时开始.*后退 2 秒.*吹泡泡 1 秒.*泡泡先停，行走再持续 1 秒/);
  assert.match(await preview.innerText(),/预计 2 秒/);
  await loadDeviceDraft([step('backward',2000,0),step('none',0,1000)]);
  assert.match(await preview.innerText(),/第 1 步 · 先后退 2 秒.*\n第 2 步 · 再吹泡泡 1 秒/);
  assert.match(await preview.innerText(),/预计 3.2 秒/);
  assert(await page.locator('#show-confirm').isDisabled());assert.equal(starts,1);
  await loadDeviceDraft([step()]);
  await page.locator('#show-reviewed').check();conflictNext=true;
  // Fresh state at confirmation must reject a revision changed by voice.
  await page.locator('#show-confirm').click();
  await page.locator('#show-notice').filter({hasText:'没有发送操作'}).waitFor();assert.equal(starts,1);
  await page.locator('#show-load').click();await page.locator('#show-cancel').click();
  await page.locator('#show-notice').filter({hasText:'设备草稿已取消'}).waitFor();assert.equal(draft,null);
  active=true;dropRelease=true;await page.evaluate(()=>poll());
  await page.locator('#message').filter({hasText:'动作序列'}).waitFor();
  const sentBeforeLoss=requests.length;
  await page.evaluate(()=>window.dispatchEvent(new Event('offline')));
  await page.locator('#message').filter({hasText:'按设备 BOOT 键'}).waitFor();
  const warning=await page.locator('#message').boundingBox();
  assert(warning.y>=0 && warning.y+warning.height<=height);
  await page.evaluate(()=>window.dispatchEvent(new Event('online')));
  await page.locator('#message').filter({hasText:'动作序列'}).waitFor();
  assert(!requests.slice(sentBeforeLoss).some(r=>r.path==='/api/action'||r.path==='/api/stop'));
  assert.deepEqual(errors,[]);await page.close();
 }
 console.log('PASS: real Chromium at 320/390/1280, local templates, single-step DOM editing, device revision preview, explicit confirmation, voice conflict and cancellation; fixed stop and offline BOOT guidance visible, fresh state after reconnect without replay; mocked transport only');
} finally {await browser.close();}
