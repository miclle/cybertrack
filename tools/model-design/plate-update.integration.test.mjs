import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp,rm,readFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';
import {createHash} from 'node:crypto';

// Isolated service/kernel verification, not desktop MCP acceptance.
test('comment spacing edit → undo preserves plate dimensions, STEP history and durable processing', {timeout:120000}, async()=>{
  const data=await mkdtemp(join(tmpdir(),'solidcue-spacing-'));
  const origin='http://127.0.0.1:19479';
  let child;
  async function start() {
    child=spawn(process.execPath,['dist/server.js'],{cwd:import.meta.dirname,env:{...process.env,
      CAD_COMMENT_DATA_DIR:data,CAD_COMMENT_PORT:'19479',CAD_COMMENT_INITIAL_MODEL:'blank',
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
  const edit=input=>request('/api/geometry/plate-hole-spacing',input);
  async function comment(text) {
    const {model}=await state();
    const saved=await request('/api/comments',{documentId:model.documentId,revision:model.revision,
      selection:{kind:'object',objectId:'plate-01'},camera:{position:[40,40,40],target:[0,0,6]},comment:text});
    assert.equal(saved.status,201);
    return {documentId:model.documentId,expectedRevision:model.revision,commentId:saved.data.id,sha256:saved.data.sha256};
  }
  try {
    await start();
    const documentId=(await state()).model.documentId;
    assert.deepEqual((await state()).stepExports,[{revision:'r1',parts:[]}]);
    assert.equal((await request('/api/export-step',{documentId,revision:'r1',partId:'assembly'})).status,400);
    assert.equal((await request('/api/geometry/mounting-plate',{documentId,expectedRevision:'r1',requestId:'spacing-base',
      lengthMm:60,widthMm:30,thicknessMm:4,holeDiameterMm:6.5,holeSpacingMm:40})).status,201);
    const baseline=await state();
    const originalStep=await (await fetch(origin+'/api/geometry/r2/plate-01.step')).text();
    const exportInput={documentId,revision:'r2',partId:'plate-01'};
    const exportBaseline=await readFile(join(data,'events.jsonl'),'utf8');
    const artifact=(await request('/api/export-step',exportInput)).data;
    assert.equal(Buffer.from(artifact.resource.blob,'base64').toString(),originalStep);
    assert.equal(artifact.sha256,createHash('sha256').update(originalStep).digest('hex'));
    const saved=(await request('/api/save-step',exportInput)).data;
    assert.equal(saved.saved,true);
    assert.equal(await readFile(saved.filePath,'utf8'),originalStep);
    assert.equal(await readFile(join(data,'events.jsonl'),'utf8'),exportBaseline);
    const request44={...await comment('双孔中心距从 40 改为 44 mm，关于板中心对称，其他尺寸不变'),holeSpacingMm:44};
    for (const patch of [{documentId:'other'},{documentId:undefined},{expectedRevision:'r1'},{sha256:'bad'},
      {commentId:'missing'},{holeSpacingMm:6.5},{holeSpacingMm:53.5},{holeSpacingMm:0},{lengthMm:70},{script:'untrusted'}]) {
      assert.ok((await edit({...request44,...patch})).status>=400);
      assert.equal((await state()).model.revision,'r2');
    }
    // Valid finite input that fails kernel validation leaves no visible partial revision.
    assert.equal((await edit({...request44,holeSpacingMm:6.5000000001})).status,400);
    assert.equal((await state()).comments[0].processing.status,'failed');
    assert.equal((await state()).model.revision,'r2');
    const concurrent=await Promise.all([edit(request44),edit(request44)]);
    assert.deepEqual(concurrent.map(r=>r.status).sort(),[200,409]);
    const wider=await state();
    assert.equal(wider.model.revision,'r3');
    assert.deepEqual(wider.model.parts[0],{...baseline.model.parts[0],holeSpacing:44});
    const geometry=wider.model.geometry.parts['plate-01'];
    assert.ok(Math.abs(geometry.volumeMm3-(7200-2*Math.PI*3.25**2*4))<1e-5);
    geometry.boundsMm.forEach((v,i)=>assert.ok(Math.abs(v-[-30,-15,0,30,15,4][i])<1e-6));
    for (const flag of ['valid','stepRoundTripValid','stepBoundsVerified','stepHoleGeometryVerified','stepHoleVoidVerified','stepWallSolidVerified','bottomAnchoredVerified']) assert.equal(geometry[flag],true,flag);
    assert.notDeepEqual(wider.preview.meshes,baseline.preview.meshes);
    assert.deepEqual(geometry.holeCentersMm,[[-22,0],[22,0]]);
    assert.ok(Math.abs(geometry.volumeMm3-baseline.model.geometry.parts['plate-01'].volumeMm3)<1e-5);
    const history=wider.history.entries.at(-1);
    assert.equal(history.type,'update-plate-hole-spacing');
    assert.equal(history.commentId,request44.commentId);
    assert.equal(history.beforeParameters.holeSpacing,40);
    assert.equal(history.afterParameters.holeSpacing,44);
    assert.equal((await edit(request44)).status,409);
    const noop={...await comment('保持孔距 44 mm'),holeSpacingMm:44};
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
    assert.equal((await edit({...request44,expectedRevision:'r4'})).status,409);
    assert.equal(await (await fetch(origin+'/api/geometry/r2/plate-01.step')).text(),originalStep);
    assert.equal((await fetch(origin+'/api/geometry/r3/plate-01.step')).status,200);
    await stop();await start();
    assert.deepEqual((await state()).model.parts,baseline.model.parts);
    assert.deepEqual((await request('/api/export-step',exportInput)).data,artifact);
    assert.equal((await request('/api/save-step',exportInput)).data.reused,true);
    const latest=(await request('/api/export-step',{...exportInput,revision:'r4'})).data;
    assert.notEqual(latest.filename,artifact.filename);
    assert.equal(latest.revision,'r4');
    const restoredSave=(await request('/api/save-step',{...exportInput,revision:'r4'})).data;
    assert.equal(restoredSave.saved,true);
    assert.equal(createHash('sha256').update(await readFile(restoredSave.filePath)).digest('hex'),latest.sha256);
    assert.deepEqual((await state()).stepExports.map(item=>item.revision),['r1','r2','r3','r4']);
    const events=(await readFile(join(data,'events.jsonl'),'utf8')).trim().split('\n').map(JSON.parse);
    assert.deepEqual(events.filter(e=>e.type==='geometry-model').map(e=>e.model.revision),['r1','r2','r3','r4']);
  } finally {await stop();await rm(data,{recursive:true,force:true});}
});
