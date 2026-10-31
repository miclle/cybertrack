import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';

test('compiled service locates Python/assets outside the caller cwd and replays its journal unchanged', {timeout:60000}, async()=>{
  const directory=await mkdtemp(join(tmpdir(),'solidcue-build-'));
  const data=join(directory,'data');
  const origin='http://127.0.0.1:19480';
  let child;
  async function start() {
    child=spawn(process.execPath,[join(import.meta.dirname,'dist/server.js')],{
      cwd:directory,env:{...process.env,CAD_COMMENT_DATA_DIR:data,CAD_COMMENT_PORT:'19480',
        CAD_COMMENT_INITIAL_MODEL:'demo',CAD_COMMENT_EXPORT_DIR:join(directory,'exports'),
        CODEX_THREAD_ID:'',CAD_CHAT_THREAD_ID:''},stdio:['ignore','pipe','pipe'],
    });
    await new Promise((resolve,reject)=>{
      let stderr='';
      const timer=setTimeout(()=>{child.kill();reject(new Error(`Startup timed out: ${stderr}`));},30000);
      child.stderr.on('data',chunk=>{stderr+=chunk;});
      child.stdout.on('data',chunk=>{if(String(chunk).includes('SolidCue:')){clearTimeout(timer);resolve();}});
      child.once('exit',code=>{clearTimeout(timer);reject(new Error(`Server exited ${code}: ${stderr}`));});
      child.once('error',error=>{clearTimeout(timer);reject(error);});
    });
  }
  async function stop() {
    if(child?.exitCode===null){const done=once(child,'exit');child.kill();await done;}
  }
  try {
    await start();
    const initial=await (await fetch(origin+'/api/state')).json();
    assert.equal(initial.model.parts.length,4);
    assert.equal(initial.model.geometry.parts['pin-01'].stepRoundTripValid,true);
    const page=await fetch(origin);
    assert.match(page.headers.get('content-type'),/text\/html/);
    const html=await page.text();
    assert.match(html,/<script type="module" src="\/app.js"><\/script>/);
    assert.doesNotMatch(html,/importmap/);
    const script=await fetch(origin+'/app.js');
    assert.match(script.headers.get('content-type'),/javascript/);
    assert.equal(await script.text(),await readFile(new URL('./dist/web/app.js',import.meta.url),'utf8'));
    assert.match(await (await fetch(origin+'/style.css')).text(),/viewport/);
    assert.equal((await fetch(origin+'/server.ts')).status,404);
    const journal=await readFile(join(data,'events.jsonl'),'utf8');
    await stop();
    await start();
    assert.deepEqual(await (await fetch(origin+'/api/state')).json(),initial);
    assert.equal(await readFile(join(data,'events.jsonl'),'utf8'),journal);
  } finally {await stop();await rm(directory,{recursive:true,force:true});}
});
