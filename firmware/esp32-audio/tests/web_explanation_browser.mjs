// Optional browser QA: use an installed Playwright module; transport is intercepted.
import {pathToFileURL} from 'node:url';
const {chromium}=await import(process.env.CYBERTRACK_PLAYWRIGHT_MODULE
 ? pathToFileURL(process.env.CYBERTRACK_PLAYWRIGHT_MODULE).href : 'playwright');
import {readFile, mkdir} from 'node:fs/promises';
import assert from 'node:assert/strict';
const html=await readFile('firmware/esp32-audio/web/index.html','utf8');
await mkdir('output/improvements',{recursive:true});
const browser=await chromium.launch({headless:true});
let sequence=0;const requests=[];
try {
 for (const [width,height] of [[390,844],[320,568],[1280,800]]) {
  const page=await browser.newPage({viewport:{width,height}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const path=new URL(route.request().url()).pathname;
   if(path==='/') return route.fulfill({contentType:'text/html',body:html});
   requests.push(path);
   if(path==='/api/pair') return route.fulfill({json:{result:'ok',token:'fake-local-only'}});
   if(path==='/api/state') return route.fulfill({json:{result:'ok',request_sequence:++sequence,window:sequence,state:'STOPPED',boot_held:false,
    capabilities:{move:true,water:true,bubbles:true,ignition:true,speed_control:true},
    move_remaining_ms:0,move_cooldown_ms:0,water_remaining_ms:0,water_cooldown_ms:0,
    bubbles_remaining_ms:0,ignition_remaining_ms:0,
    recent_command:{valid:true,operation:'move',result:'not_ready_or_busy',source:'voice',age_ms:300},
    proximity:{forward_blocked:false,auto_avoidance_enabled:false}}});
   return route.abort();
  });
  await page.goto('http://cybertrack.test/');
  await page.locator('#connection').filter({hasText:'已连接'}).waitFor();
  await page.screenshot({path:`output/improvements/ct43-${width}-closed.png`,fullPage:true});
  await page.locator('#help summary').click();
  await page.locator('#diagnosis').filter({hasText:'回执未细分原因'}).waitFor();
  assert(await page.locator('#stop').isVisible());
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
  await page.locator('#help .note').scrollIntoViewIfNeeded();
  await page.evaluate(()=>scrollTo(0,document.body.scrollHeight));
  const note=await page.locator('#help .note').boundingBox(), dock=await page.locator('.stop-bar').boundingBox();
  assert(note.y+note.height<=dock.y+1);
  await page.screenshot({path:`output/improvements/ct43-${width}-help.png`});
  assert.deepEqual(errors,[]);
  await page.close();
 }
 assert(!requests.includes('/api/action'));
 console.log('PASS: real Chromium 320/390/1280 layout, help disclosure, no overflow or JS errors; mocked transport, no action requests');
} finally {await browser.close();}
