import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,writeFile,mkdir,rm,realpath,symlink,copyFile} from 'node:fs/promises';
import {join} from 'node:path';
import {tmpdir} from 'node:os';
import {spawnSync} from 'node:child_process';
import {createHash,randomUUID} from 'node:crypto';
import {blankModel,validateComment} from './dist/model.js';
import {prepareCadSync} from './dist/cad-bridge.js';
import {operationHistory,prepareUndo} from './dist/history.js';
const root=import.meta.dirname;
test('external STEP snapshots fence identity, versions, face mapping and native restore', {timeout:60000}, async()=>{
  const temp=await realpath(await mkdtemp(join(tmpdir(),'solidcue-cad-')));
  const inbox=join(temp,'inbox'), data=join(temp,'data');
  await mkdir(inbox);await mkdir(data);
  const source={application:'FreeCAD',documentName:'Test',documentUid:randomUUID(),objectName:'Box'};
  // Import the real kernel once for all fixture sizes, rather than per request.
  const fixtures=join(temp,'fixtures');await mkdir(fixtures);
  const generated=spawnSync(join(root,'.venv/bin/python'),['-c',[
    'import cadquery as cq,json,sys',
    'from pathlib import Path',
    'from geometry import bounds',
    'root=Path(sys.argv[1])',
    'for height in [8,10,12]:',
    ' s=cq.Solid.makeBox(60,30,height)',
    ' cq.exporters.export(s,str(root/f"{height}.step"))',
    ' (root/f"{height}.json").write_text(json.dumps([{\'id\':f\'Face{i+1}\',\'area\':f.Area(),\'center\':f.Center().toTuple(),\'bounds\':bounds(f)} for i,f in enumerate(s.Faces())]))',
  ].join('\n'),fixtures],{cwd:root,encoding:'utf8'});
  assert.equal(generated.status,0,generated.stderr);
  async function snapshot(id,height,kind,previous=null,before={},after={}) {
    const folder=join(inbox,id);await mkdir(folder);
    await copyFile(join(fixtures,height+'.step'),join(folder,'model.step'));
    const step=await readFile(join(folder,'model.step'));
    const manifest={schema:'solidcue-freecad/v1',snapshotId:id,kind,
      source:{...source,fingerprint:createHash('sha256').update(String(height)).digest('hex')},
      name:'Test block',unit:'mm',upAxis:'Z',stepSha256:createHash('sha256').update(step).digest('hex'),
      previousFingerprint:previous,before,after,properties:{Height:height},faces:JSON.parse(await readFile(join(fixtures,height+'.json'),'utf8'))};
    await writeFile(join(folder,'manifest.json'),JSON.stringify(manifest));
    return manifest;
  }
  try {
    let model=blankModel('test-cad'), revisions=new Map([[model.revision,model]]), comments=new Map();
    const baseline=await snapshot('base',8,'snapshot');
    const request=()=>({documentId:model.documentId,expectedRevision:model.revision});
    const apply=async(input)=>{model=await prepareCadSync({...request(),...input},model,comments,revisions,root,data,inbox);revisions.set(model.revision,model);};
    await assert.rejects(()=>prepareCadSync({...request(),snapshotId:'../escape',mode:'attach'},model,comments,revisions,root,data,inbox));
    await apply({snapshotId:'base',mode:'attach'});
    assert.equal(model.parts[0].kind,'step');
    assert.equal(operationHistory(revisions).undoOperationId,null);
    assert.throws(()=>prepareUndo({...request(),operationId:'r2'},model,revisions),/原生文档/);
    const preview=JSON.parse(await readFile(join(data,'geometry',model.geometry.key,'preview.json')));
    assert.equal(preview.meshes['external-01'].faces.length,6);
    const face=preview.meshes['external-01'].faces[0];
    const payload=validateComment({documentId:model.documentId,revision:model.revision,
      selection:{kind:'surface',objectId:'external-01',surface:'+X',faceId:face.id,triangleIndex:face.start,
        worldPoint:[0,15,4],localPoint:[0,15,4],worldNormal:[-1,0,0]},
      camera:{position:[100,100,100],target:[0,0,0]},comment:'Height 改为 12 mm'},model,preview);
    const comment={id:randomUUID(),sha256:'b'.repeat(64),payload,receipt:null};
    comments.set(comment.id,comment);
    await snapshot('edit',12,'edit',baseline.source.fingerprint,{Height:8},{Height:12});
    await assert.rejects(()=>prepareCadSync({...request(),snapshotId:'edit',mode:'edit',commentId:comment.id,sha256:'c'.repeat(64)},model,comments,revisions,root,data,inbox),/校验值/);
    const editPath=join(inbox,'edit','manifest.json');
    const editManifest=JSON.parse(await readFile(editPath));
    await writeFile(editPath,JSON.stringify({...editManifest,before:{Height:9}}));
    await assert.rejects(()=>prepareCadSync({...request(),snapshotId:'edit',mode:'edit',commentId:comment.id,sha256:comment.sha256},model,comments,revisions,root,data,inbox),/属性变化/);
    await writeFile(editPath,JSON.stringify(editManifest));
    await apply({snapshotId:'edit',mode:'edit',commentId:comment.id,sha256:comment.sha256});
    assert.equal(model.geometry.parts['external-01'].volumeMm3,21600);
    assert.equal(operationHistory(revisions).undoOperationId,'r3');
    const undo=await snapshot('undo',8,'undo',model.parts[0].source.fingerprint,{Height:12},{Height:8});
    undo.undoSnapshotId='edit';
    await writeFile(join(inbox,'undo','manifest.json'),JSON.stringify(undo));
    await apply({snapshotId:'undo',mode:'undo',operationId:'r3'});
    assert.equal(model.parts[0].properties.Height,8);
    assert.equal(model.geometry.parts['external-01'].volumeMm3,14400);
    assert.equal(operationHistory(revisions).entries.find(e=>e.id==='r3').status,'undone');
    const invalid=await snapshot('invalid',10,'snapshot');
    invalid.faces[1]=invalid.faces[0];
    await writeFile(join(inbox,'invalid','manifest.json'),JSON.stringify(invalid));
    await assert.rejects(()=>prepareCadSync({...request(),snapshotId:'invalid',mode:'refresh'},model,comments,revisions,root,data,inbox),/面|mapping/);
    const mismatch=await snapshot('wrong-source',10,'snapshot');
    mismatch.source.documentUid=randomUUID();
    await writeFile(join(inbox,'wrong-source','manifest.json'),JSON.stringify(mismatch));
    await assert.rejects(()=>prepareCadSync({...request(),snapshotId:'wrong-source',mode:'refresh'},model,comments,revisions,root,data,inbox),/来源/);
    await writeFile(join(inbox,'base','model.step'),'tampered');
    await assert.rejects(()=>prepareCadSync({...request(),snapshotId:'base',mode:'refresh'},model,comments,revisions,root,data,inbox),/哈希/);
    await symlink(join(inbox,'undo'),join(inbox,'linked'));
    await assert.rejects(()=>prepareCadSync({...request(),snapshotId:'linked',mode:'refresh'},model,comments,revisions,root,data,inbox),/符号链接/);
    await assert.rejects(()=>prepareCadSync({...request(),expectedRevision:'r1',snapshotId:'undo',mode:'refresh'},model,comments,revisions,root,data,inbox),/版本/);
  } finally {await rm(temp,{recursive:true,force:true});}
});
