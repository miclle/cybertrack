// Render the shipped controller; synthetic HTTP only, no device access.
import assert from 'node:assert/strict';
import {readFile, mkdir} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(process.env.CYBERTRACK_PLAYWRIGHT_MODULE
  ? pathToFileURL(process.env.CYBERTRACK_PLAYWRIGHT_MODULE).href : 'playwright');
const html=await readFile('firmware/esp32-audio/web/index.html','utf8');
await mkdir('output/improvements/ct78-browser',{recursive:true});
const browser=await chromium.launch({headless:true});
try {
  for (const width of [320,390,1280]) {
    const page=await browser.newPage({viewport:{width,height:844}}), errors=[], actions=[];
    page.on('pageerror',e=>errors.push(String(e)));
    let seq=0, active=true;
    const status=()=>({result:'ok',request_sequence:++seq,window:seq,state:active?'ACTIVE':'STOPPED',fault:'none',boot_held:false,
      capabilities:{move:true,water:true,bubbles:true,ignition:true,frenzy:true,speed_control:true,water_hold:true,bubbles_hold:true},
      sequence_active:active,sequence_step:1,sequence_steps:2,sequence_result:active?'waiting':'cancelled',sequence_source:active?'voice':'none',
      move_remaining_ms:0,water_remaining_ms:0,bubbles_remaining_ms:0,ignition_remaining_ms:0,
      move_cooldown_ms:0,water_cooldown_ms:0,bubbles_cooldown_ms:0,ignition_cooldown_ms:0,
      web_speed_percent:100,move_speed_percent:0,move_direction:'none',logical_outputs:{left:0,right:0,water:false,bubbles:false,ignition:false},
      drive_hold_id:0,water_hold_id:0,bubbles_hold_id:0,frenzy_remaining_ms:0,
      distance:{valid:true,error:'none',distance_mm:600,age_ms:0},proximity:{auto_avoidance_enabled:false,forward_blocked:false}});
    await page.route('**/*',async route=>{
      const url=new URL(route.request().url());
      assert.equal(url.host,'controller.test');
      if (url.pathname==='/') return route.fulfill({contentType:'text/html',body:html});
      if (url.pathname==='/api/pair') return route.fulfill({json:{result:'ok',token:'synthetic'}});
      if (url.pathname==='/api/stop') {active=false;actions.push('stop');}
      else assert.equal(url.pathname,'/api/state');
      return route.fulfill({json:status()});
    });
    await page.goto('http://controller.test/');
    await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('等待下一步'));
    assert.equal(await page.locator('#theatre,[id^="show-"]').count(),0);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    await page.locator('#stop').click();
    await page.waitForFunction(()=>document.querySelector('#message').textContent.includes('全部停止'));
    assert.deepEqual(actions,['stop']);assert.deepEqual(errors,[]);
    await page.screenshot({path:`output/improvements/ct78-browser/controller-${width}.png`,fullPage:true});
    await page.close();
  }
  console.log('PASS: 320/390/1280 px controller, no theatre DOM, voice-sequence wait and global stop; synthetic HTTP only');
} finally {await browser.close();}
