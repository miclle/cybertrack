// Exercise the generated file in Chromium. No board, microphone, network or family data.
import assert from 'node:assert/strict';
import {resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(process.env.CYBERTRACK_PLAYWRIGHT_MODULE
  ? pathToFileURL(process.env.CYBERTRACK_PLAYWRIGHT_MODULE).href : 'playwright');
const browser=await chromium.launch();
try{
  for(const width of [320,390,1280]){
    const page=await browser.newPage({viewport:{width,height:800}});
    const requests=[], errors=[];
    page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
    page.on('pageerror',e=>errors.push(String(e)));
    await page.goto(pathToFileURL(resolve(process.argv[2]||'output/family-study/rehearsal.html')).href);
    await page.context().setOffline(true);
    const el=id=>page.locator('#'+id);
    assert(await el('paper').isVisible());assert(await el('frenzy-5').isHidden());
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    for(const preset of ['celebrate','curtain','entry'])await el('show-'+preset).click();
    assert.match(await el('paper-stage').innerText(),/当一次导演/);
    await el('show-step').fill('2');await el('show-step').press('Tab');
    await el('show-bubbles').fill('2');await el('show-apply').click();await el('show-save').click();
    await el('show-notice').filter({hasText:'预览设备草稿'}).waitFor();
    assert.match(await el('show-preview').innerText(),/吹泡泡 2 秒/);assert(await el('show-confirm').isDisabled());
    await el('show-reviewed').check();await el('show-confirm').click();
    await el('paper-stage').filter({hasText:'第 2 步 · 吹泡泡'}).waitFor();await el('stop').click();
    await el('paper-stage').filter({hasText:'已停止'}).waitFor();
    await el('show-curtain').click();await el('show-save').click();await el('show-reviewed').check();await el('show-confirm').click();
    await el('paper-stage').filter({hasText:'排演结束'}).waitFor();assert(await el('show-confirm').isDisabled());
    assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);await page.close();
  }
  console.log('PASS: offline file at 320/390/1280, three templates, single-step edit, exact preview, confirmation, live second step, stop, fresh replay, natural finish, zero HTTP requests.');
}finally{await browser.close();}
