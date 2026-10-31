import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {mkdtemp,rm,appendFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {once} from 'node:events';

// Isolated journal/artifacts and loopback port: never edits the live user model.
test('real solid edits and undo are atomic, version fenced, durable, and restore the original mesh', {timeout:120000}, async()=>{
  const data=await mkdtemp(join(tmpdir(),'cad-history-'));
  const port=19473,origin=`http://127.0.0.1:${port}`;
  let child;
  async function start(){
    child=spawn(process.execPath,['dist/server.js'],{cwd:import.meta.dirname,env:{...process.env,CAD_COMMENT_PORT:String(port),CAD_COMMENT_DATA_DIR:data,CODEX_THREAD_ID:'',CAD_CHAT_THREAD_ID:''},stdio:['ignore','pipe','pipe']});
    await new Promise((resolve,reject)=>{
      const timer=setTimeout(()=>reject(new Error('Test server startup timed out')),30000);
      child.stdout.on('data',b=>{if(String(b).includes('SolidCue:')){clearTimeout(timer);resolve();}});
      child.once('exit',code=>{clearTimeout(timer);reject(new Error(`Test server exited ${code}`));});
      child.once('error',reject);
    });
  }
  async function stop(){if(child?.exitCode===null){const done=once(child,'exit');child.kill();await done;}}
  async function request(path,input){const r=await fetch(origin+path,input?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)}:{});return {status:r.status,data:await r.json()};}
  const state=async()=> (await request('/api/state')).data;
  try {
    await start();const baseline=await state();
    async function edit(diameter){
      const s=await state();
      const c=(await request('/api/comments',{documentId:s.model.documentId,revision:s.model.revision,selection:{kind:'object',objectId:'knob-01',objectName:'压紧旋钮'},camera:{position:[190,250,180],target:[0,0,27]},comment:`Test hole ${diameter} mm`})).data;
      if(diameter===8) {
        const invalid=await request('/api/geometry/center-hole',{documentId:'cad-comment-demo',expectedRevision:s.model.revision,commentId:c.id,sha256:c.sha256,diameterMm:40});
        assert.equal(invalid.status,400);assert.equal((await state()).model.revision,s.model.revision);
        assert.equal((await state()).comments.find(x=>x.id===c.id).processing.status,'failed');
      }
      const result=await request('/api/geometry/center-hole',{documentId:'cad-comment-demo',expectedRevision:s.model.revision,commentId:c.id,sha256:c.sha256,diameterMm:diameter});
      assert.equal(result.status,200);assert.equal(result.data.geometry.stepRoundTripValid,true);
      assert.equal((await state()).comments.find(x=>x.id===c.id).processing.status,'completed');
      return c;
    }
    await edit(8);const eight=await state();const c=await edit(10);
    const ten=await state();assert.equal(ten.history.undoOperationId,'r3');
    assert.deepEqual(ten.history.entries.map(e=>[e.beforeDiameterMm,e.afterDiameterMm]),[[0,8],[8,10]]);
    assert.equal((await request('/api/geometry/undo',{documentId:'cad-comment-demo',expectedRevision:'r2',operationId:'r3'})).status,409);
    assert.equal((await request('/api/geometry/undo',{documentId:'cad-comment-demo',expectedRevision:'r3',operationId:'r2'})).status,409);
    const [undo,duplicate]=await Promise.all([request('/api/geometry/undo',{documentId:'cad-comment-demo',expectedRevision:'r3',operationId:'r3'}),request('/api/geometry/undo',{documentId:'cad-comment-demo',expectedRevision:'r3',operationId:'r3'})]);
    assert.deepEqual([undo.status,duplicate.status].sort(),[200,409]);
    const restored=await state();assert.equal(restored.model.revision,'r4');assert.deepEqual(restored.preview.meshes,eight.preview.meshes);
    assert.equal((await fetch(origin+'/api/geometry/r3/knob-01.step')).status,200);
    await stop();
    await appendFile(join(data,'events.jsonl'),JSON.stringify({type:'processing',id:c.id,processing:{status:'processing'}})+'\n');
    await start();const replay=await state();assert.equal(replay.model.revision,'r4');assert.equal(replay.history.undoOperationId,'r2');
    assert.equal(replay.comments.find(x=>x.id===c.id).processing.status,'failed');
    assert.equal((await request('/api/geometry/undo',{documentId:'cad-comment-demo',expectedRevision:'r4',operationId:'r2'})).status,200);
    const original=await state();assert.equal(original.model.revision,'r5');assert.equal(original.history.undoOperationId,null);assert.deepEqual(original.preview.meshes,baseline.preview.meshes);
  } finally {await stop();await rm(data,{recursive:true,force:true});}
});
