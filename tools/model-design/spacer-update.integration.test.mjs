import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp,rm,readFile,writeFile,readdir} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
import {createHash} from 'node:crypto';

// Isolated service/kernel verification, not desktop MCP acceptance.
test('comment height update → undo preserves bottom, STEP history and durable processing', {timeout:120000}, async()=>{
  const data=await mkdtemp(join(tmpdir(),'solidcue-height-'));
  const origin='http://127.0.0.1:19476';
  let child;
  async function start() {
    child=spawn(process.execPath,['dist/server.js'],{cwd:import.meta.dirname,env:{...process.env,
      CAD_COMMENT_DATA_DIR:data,CAD_COMMENT_PORT:'19476',CAD_COMMENT_INITIAL_MODEL:'blank',
      CAD_COMMENT_EXPORT_DIR:join(data,'exports'),
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
  const edit=input=>request('/api/geometry/spacer-parameters',input);
  async function comment(text) {
    const {model}=await state();
    const saved=await request('/api/comments',{documentId:model.documentId,revision:model.revision,
      selection:{kind:'object',objectId:'spacer-01'},camera:{position:[40,40,40],target:[0,0,6]},comment:text});
    assert.equal(saved.status,201);
    return {documentId:model.documentId,expectedRevision:model.revision,commentId:saved.data.id,sha256:saved.data.sha256};
  }
  try {
    await start();
    const documentId=(await state()).model.documentId;
    assert.deepEqual((await state()).stepExports,[{revision:'r1',parts:[]}]);
    assert.equal((await request('/api/export-step',{documentId,revision:'r1',partId:'assembly'})).status,400);
    assert.equal((await request('/api/geometry/spacer',{documentId,expectedRevision:'r1',requestId:'height-base',
      outerDiameterMm:20,holeDiameterMm:6.5,heightMm:12})).status,201);
    const baseline=await state();
    const originalStep=await (await fetch(origin+'/api/geometry/r2/spacer-01.step')).text();
    const exportInput={documentId,revision:'r2',partId:'spacer-01'};
    const exportBaseline=await readFile(join(data,'events.jsonl'),'utf8');
    for (const patch of [{documentId:'other'},{documentId:undefined},{revision:'r99'},{revision:'r1'},
      {revision:'../r2'},{partId:'../events'},{partId:'pin-01'},{extra:true}]) {
      assert.ok((await request('/api/export-step',{...exportInput,...patch})).status>=400);
    }
    const artifact=(await request('/api/export-step',exportInput)).data;
    assert.equal(Buffer.from(artifact.resource.blob,'base64').toString(),originalStep);
    assert.equal(artifact.sha256,createHash('sha256').update(originalStep).digest('hex'));
    assert.equal(artifact.byteLength,Buffer.byteLength(originalStep));
    assert.match(artifact.filename,/^solidcue-[a-f0-9]{12}-r2-spacer-01\.step$/);
    assert.equal(artifact.resource.uri,`file:///${artifact.filename}`);
    assert.equal(artifact.resource.mimeType,'application/step');
    const download=await fetch(origin+'/api/download-step?'+new URLSearchParams(exportInput));
    assert.equal(download.status,200);
    assert.equal(download.headers.get('content-type'),'application/step');
    assert.equal(download.headers.get('content-disposition'),`attachment; filename="${artifact.filename}"`);
    assert.equal(await download.text(),originalStep);
    for(const patch of [{documentId:'other'},{revision:'r1'},{partId:'../events'}]) {
      assert.ok((await fetch(origin+'/api/download-step?'+new URLSearchParams({...exportInput,...patch}))).status>=400);
    }
    assert.equal((await request('/api/export-step',{...exportInput,partId:'assembly'})).status,200);
    for(const patch of [{documentId:'other'},{revision:'r1'},{partId:'../events'},{filePath:'/untrusted'}]) {
      assert.ok((await request('/api/save-step',{...exportInput,...patch})).status>=400);
    }
    const saves=await Promise.all([request('/api/save-step',exportInput),request('/api/save-step',exportInput)]);
    assert.deepEqual(saves.map(r=>r.status),[200,200]);
    assert.deepEqual(saves.map(r=>r.data.reused).sort(),[false,true]);
    const saved=saves[0].data;
    assert.equal(saved.filePath,join(data,'exports',artifact.filename));
    assert.equal(saved.saved,true);
    assert.equal(saved.sha256,artifact.sha256);
    assert.equal(await readFile(saved.filePath,'utf8'),originalStep);
    await writeFile(saved.filePath,'existing user file');
    assert.equal((await request('/api/save-step',exportInput)).status,400);
    assert.equal(await readFile(saved.filePath,'utf8'),'existing user file');
    assert.deepEqual(await readdir(join(data,'exports')),[artifact.filename]);
    await rm(saved.filePath);
    assert.equal((await request('/api/save-step',exportInput)).status,200);
    assert.equal(await readFile(join(data,'events.jsonl'),'utf8'),exportBaseline);
    const request16={...await comment('加高 4 mm，底面不动，直径不变'),heightMm:16};
    for (const patch of [{documentId:'other'},{documentId:undefined},{expectedRevision:'r1'},{sha256:'bad'},
      {commentId:'missing'},{holeDiameterMm:20},{heightMm:0},{script:'untrusted'}]) {
      assert.ok((await edit({...request16,...patch})).status>=400);
      assert.equal((await state()).model.revision,'r2');
    }
    // Valid finite input that fails kernel validation leaves no visible partial revision.
    assert.equal((await edit({...request16,heightMm:1e-10})).status,400);
    assert.equal((await state()).comments[0].processing.status,'failed');
    assert.equal((await state()).model.revision,'r2');
    const concurrent=await Promise.all([edit(request16),edit(request16)]);
    assert.deepEqual(concurrent.map(r=>r.status).sort(),[200,409]);
    const taller=await state();
    assert.equal(taller.model.revision,'r3');
    assert.deepEqual(taller.model.parts[0],{...baseline.model.parts[0],height:16,position:[0,0,8]});
    const geometry=taller.model.geometry.parts['spacer-01'];
    assert.ok(Math.abs(geometry.volumeMm3-Math.PI*(100-3.25**2)*16)<1e-5);
    geometry.boundsMm.forEach((v,i)=>assert.ok(Math.abs(v-[-10,-10,0,10,10,16][i])<1e-6));
    for (const flag of ['valid','stepRoundTripValid','stepBoundsVerified','stepHoleVoidVerified','stepWallSolidVerified','bottomAnchoredVerified']) assert.equal(geometry[flag],true,flag);
    assert.notDeepEqual(taller.preview.meshes,baseline.preview.meshes);
    const history=taller.history.entries.at(-1);
    assert.equal(history.type,'update-spacer-parameters');
    assert.equal(history.commentId,request16.commentId);
    assert.equal(history.beforeParameters.height,12);
    assert.equal(history.afterParameters.height,16);
    assert.equal((await edit(request16)).status,409);
    const noop={...await comment('保持高度 16 mm'),heightMm:16};
    const unchanged=await edit(noop);
    assert.equal(unchanged.status,200);
    assert.equal(unchanged.data.changed,false);
    assert.equal(unchanged.data.revision,'r3');
    assert.equal((await edit(noop)).status,409);
    await stop();await start();
    const replay=await state();
    assert.equal(replay.model.revision,'r3');
    assert.equal(replay.comments[0].processing.status,'completed');
    assert.equal(replay.comments[1].processing.changed,false);
    assert.equal((await edit(noop)).status,409);
    const undo=await request('/api/geometry/undo',{documentId,expectedRevision:'r3',operationId:'r3'});
    assert.equal(undo.status,200);
    const restored=await state();
    assert.equal(restored.model.revision,'r4');
    assert.deepEqual(restored.model.parts,baseline.model.parts);
    assert.deepEqual(restored.preview.meshes,baseline.preview.meshes);
    assert.equal(restored.history.entries.find(entry=>entry.id==='r3').status,'undone');
    assert.equal((await edit({...request16,expectedRevision:'r4'})).status,409);
    assert.equal(await (await fetch(origin+'/api/geometry/r2/spacer-01.step')).text(),originalStep);
    assert.equal((await fetch(origin+'/api/geometry/r3/spacer-01.step')).status,200);
    await stop();await start();
    assert.deepEqual((await state()).model.parts,baseline.model.parts);
    assert.deepEqual((await request('/api/export-step',exportInput)).data,artifact);
    assert.equal((await request('/api/save-step',exportInput)).data.reused,true);
    const latest=(await request('/api/export-step',{...exportInput,revision:'r4'})).data;
    assert.notEqual(latest.filename,artifact.filename);
    assert.equal(latest.revision,'r4');
    assert.deepEqual((await state()).stepExports.map(item=>item.revision),['r1','r2','r3','r4']);
    const events=(await readFile(join(data,'events.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
    assert.deepEqual(events.filter(e=>e.type==='geometry-model').map(e=>e.model.revision),['r1','r2','r3','r4']);
  } finally {await stop();await rm(data,{recursive:true,force:true});}
});
