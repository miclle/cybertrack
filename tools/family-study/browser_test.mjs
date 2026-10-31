// Run the real, offline observer page. Only synthetic forms are filled.
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {pathToFileURL} from 'node:url';
const {chromium}=await import(process.env.CYBERTRACK_PLAYWRIGHT_MODULE
  ? pathToFileURL(process.env.CYBERTRACK_PLAYWRIGHT_MODULE).href : 'playwright');
const fields=JSON.parse(await readFile(new URL('../../docs/validation/templates.json',import.meta.url),'utf8')).family_session_fields;
const browser=await chromium.launch({headless:true});
try {
  for(const width of [320,390,1280]){
    const page=await browser.newPage({viewport:{width,height:800},acceptDownloads:true});
    const requests=[],errors=[];
    page.on('request',r=>{if(/^https?:/.test(r.url())) requests.push(r.url());});
    page.on('pageerror',e=>errors.push(String(e)));
    await page.goto(new URL('./observer.html',import.meta.url).href);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    const input=name=>page.locator('[name="'+name+'"]');
    for(const [name,val] of Object.entries({evidence_kind:'dry_run',anonymous_id:'F01',prototype_or_device:'prototype',
                                            parent_present:'yes',first_use:'yes'})) await input(name).selectOption(val);
    for(const [name,val] of Object.entries({firmware:'ct53',cohort_id:'fixture',condition_id:'offline'})) await input(name).fill(val);
    assert(await input('custom').isDisabled());
    await page.locator('#start').click();
    await page.getByText('下载本家庭记录',{exact:true}).click();
    assert.match(await page.locator('#notice').textContent(),/先结束计时/);
    await page.locator('#end').click();
    assert(Number(await input('first_use_seconds').inputValue())>0);
    await input('free_play_observed').selectOption('yes');
    await page.getByLabel('左转一秒',{exact:true}).check();
    await page.locator('#modify').getByLabel('登场',{exact:true}).check();
    await input('custom').fill('B01 B02 B01');
    async function download(){
      const event=page.waitForEvent('download');
      await page.getByText('下载本家庭记录',{exact:true}).click();
      const file=await event;
      assert.equal(file.suggestedFilename(),'CyberTrack-F01-prototype.json');
      const [row]=JSON.parse(await readFile(await file.path(),'utf8')).family_sessions;
      return row;
    }
    const row=await download();
    assert.deepEqual(Object.keys(row).sort(),fields.slice().sort());
    assert.deepEqual(row.repeat_plays,['左转一秒','自编/B01','自编/B02']);assert.deepEqual(row.modified_shows,['登场']);
    assert.equal(row.help_count,null);assert.equal(row.first_action_completed,null);assert.equal(row.evidence_kind,'dry_run');
    await input('free_play_observed').selectOption('no');
    const incomplete=await download();assert.equal(incomplete.repeat_plays,null);assert.equal(incomplete.modified_shows,null);
    assert.deepEqual(requests,[]);assert.deepEqual(errors,[]);
    await page.close();
  }
  console.log('PASS: 320/390/1280px observer form, real timer, two JSON downloads per viewport, unknowns retained, no HTTP requests.');
} finally {await browser.close();}
