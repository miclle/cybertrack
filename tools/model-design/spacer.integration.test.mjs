import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp,rm,readFile,readdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';

// HTTP here exercises the isolated service, never substitutes for desktop MCP acceptance.
test('blank → spacer → blank is atomic, idempotent, document fenced and durable', {timeout:120000}, async()=>{
  const data=await mkdtemp(join(tmpdir(),'solidcue-spacer-'));
  const origin='http://127.0.0.1:19474';
  let child;
  async function start(initial='blank') {
    child=spawn(process.execPath,['dist/server.js'],{cwd:import.meta.dirname,env:{...process.env,
      CAD_COMMENT_DATA_DIR:data,CAD_COMMENT_PORT:'19474',CAD_COMMENT_INITIAL_MODEL:initial,
      CODEX_THREAD_ID:'',CAD_CHAT_THREAD_ID:''},stdio:['ignore','pipe','pipe']});
    await new Promise((resolve,reject)=>{
      let stderr='';
      const timer=setTimeout(()=>{child.kill();reject(new Error(`Startup timed out: ${stderr}`));},30000);
      child.stderr.on('data',b=>{stderr+=b;});
      child.stdout.on('data',b=>{if(String(b).includes('SolidCue:')){clearTimeout(timer);resolve();}});
      child.once('exit',code=>{clearTimeout(timer);reject(new Error(`Server exited ${code}: ${stderr}`));});
      child.once('error',error=>{clearTimeout(timer);reject(error);});
    });
  }
  async function stop(){if(child?.exitCode===null){const done=once(child,'exit');child.kill();await done;}}
  async function request(path,input) {
    const response=await fetch(origin+path,input?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)}:{});
    return {status:response.status,data:await response.json()};
  }
  const state=async()=> (await request('/api/state')).data;
  try {
    await start();
    const blank=await state(), documentId=blank.model.documentId;
    assert.notEqual(documentId,'cad-comment-demo');
    assert.deepEqual(blank.model.parts,[]);
    assert.deepEqual(blank.preview.meshes,{});
    const input={documentId,expectedRevision:'r1',requestId:'spacer-test-01',outerDiameterMm:20,holeDiameterMm:6.5,heightMm:12};
    for(const patch of [{documentId:'other'},{documentId:undefined},{expectedRevision:'r9'},{holeDiameterMm:20},{heightMm:0}]) {
      assert.ok((await request('/api/geometry/spacer',{...input,...patch})).status>=400);
    }
    assert.equal((await request('/api/geometry/r1/assembly.step')).status,404);
    // A finite input that OCCT cannot construct must not publish a partial model.
    const failed=await request('/api/geometry/spacer',{...input,outerDiameterMm:1e308});
    assert.equal(failed.status,400);
    assert.equal((await state()).model.revision,'r1');
    const results=await Promise.all([request('/api/geometry/spacer',input),request('/api/geometry/spacer',input)]);
    assert.deepEqual(results.map(r=>r.status).sort(),[201,409]);
    const created=await state();
    assert.equal(created.model.revision,'r2');
    assert.equal(created.model.parts.length,1);
    assert.deepEqual(created.model.parts[0].position,[0,0,6]);
    const geometry=created.model.geometry.parts['spacer-01'];
    assert.equal(geometry.solids,1);
    assert.ok(Math.abs(geometry.volumeMm3-Math.PI*(100-3.25**2)*12)<1e-5);
    geometry.boundsMm.forEach((v,i)=>assert.ok(Math.abs(v-[-10,-10,0,10,10,12][i])<1e-6));
    for(const key of ['valid','stepRoundTripValid','stepHoleVoidVerified','stepWallSolidVerified','stepBoundsVerified','bottomAnchoredVerified']) assert.equal(geometry[key],true,key);
    assert.ok(created.preview.meshes['spacer-01'].indices.length);
    assert.equal((await request('/api/geometry/spacer',input)).data.replayed,true);
    assert.equal((await request('/api/geometry/spacer',{...input,heightMm:16})).status,409);
    assert.equal((await request('/api/geometry/spacer',{...input,requestId:'another',expectedRevision:'r2'})).status,409);
    const undo={documentId,expectedRevision:'r2',operationId:'r2'};
    for(const patch of [{documentId:'other'},{documentId:undefined},{expectedRevision:'r1'},{operationId:'r1'}]) {
      assert.equal((await request('/api/geometry/undo',{...undo,...patch})).status,409);
    }
    const step=await (await fetch(origin+'/api/geometry/r2/spacer-01.step')).text();
    assert.ok(step.startsWith('ISO-10303-21'));
    assert.equal((await fetch(origin+'/api/geometry/r2/unknown.step')).status,404);
    assert.equal((await fetch(origin+'/api/geometry/r2/%2e%2e%2fevents.jsonl.step')).status,404);
    await stop();await start('demo'); // Initialization mode never resets an existing document.
    assert.equal((await state()).model.documentId,documentId);
    assert.equal((await request('/api/geometry/spacer',input)).data.replayed,true);
    assert.equal((await request('/api/geometry/undo',undo)).status,200);
    const restored=await state();
    assert.equal(restored.model.revision,'r3');
    assert.deepEqual(restored.model.parts,[]);
    assert.deepEqual(restored.preview.meshes,{});
    assert.equal(restored.history.undoOperationId,null);
    assert.equal(restored.history.entries[0].status,'undone');
    assert.deepEqual(await readdir(join(data,'geometry',restored.model.geometry.key)),['preview.json']);
    assert.equal((await request('/api/geometry/r3/assembly.step')).status,404);
    assert.equal(await (await fetch(origin+'/api/geometry/r2/spacer-01.step')).text(),step);
    await stop();await start();
    const replay=await request('/api/geometry/spacer',input);
    assert.equal(replay.data.status,'undone');
    assert.equal(replay.data.revision,'r2');
    assert.equal(replay.data.currentRevision,'r3');
    assert.deepEqual((await state()).model.parts,[]);
    const events=(await readFile(join(data,'events.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
    assert.deepEqual(events.map(e=>e.model.revision),['r1','r2','r3']);
    const second=await request('/api/geometry/spacer',{...input,expectedRevision:'r3',requestId:'spacer-test-02'});
    assert.equal(second.status,201);
    assert.equal(second.data.revision,'r4');
  } finally {await stop();await rm(data,{recursive:true,force:true});}
});
