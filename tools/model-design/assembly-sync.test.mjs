import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,mkdir,writeFile,rm,realpath} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {randomUUID,createHash} from 'node:crypto';
import {prepareCadSync} from './dist/cad-bridge.js';
import {blankModel,validateComment} from './dist/model.js';
import {readPreview} from './dist/geometry-store.js';
const hash=x=>createHash('sha256').update(x).digest('hex');
test('assembly publication fences identity, target, surrounding parts, mesh and undo',async()=>{
 const dir=await realpath(await mkdtemp(join(tmpdir(),'cybertrack-assembly-'))), inbox=join(dir,'inbox');await mkdir(inbox);
 const uid=randomUUID(), comments=new Map(), revisions=new Map();let model=blankModel('assembly-test');revisions.set('r1',model);
 const mesh=Buffer.from(JSON.stringify({positions:[0,0,0,1,0,0,0,1,0],indices:[0,1,2],faces:[{id:'Face1',type:'native',start:0,count:1}]}));
 const part=(id,z)=>({id,name:id,kind:'native',position:[0,0,0],color:'#889e96',source:{application:'FreeCAD',documentName:'Study',documentUid:uid,objectName:id,fingerprint:hash(id+z)},properties:{PlacementX:0,PlacementY:0,PlacementZ:z},meshSha256:hash(mesh),geometry:{valid:true,solids:1,volumeMm3:1,faces:1,boundsMm:[0,0,z,1,1,z+1],stepRoundTripValid:false,stepBoundsVerified:false}});
 let serial=0;
 async function snapshot(z,kind='snapshot',change={}){
  const snapshotId='s'+(++serial),parts=[part('A',z),part('B',0)], native=Buffer.from('synthetic protocol fixture; not a CAD acceptance');
  const m={schema:'cybertrack-assembly/v1',snapshotId,kind,name:'Study',unit:'mm',upAxis:'Z',parts,nativeSha256:hash(native),sceneFingerprint:hash(JSON.stringify(Object.fromEntries(parts.map(p=>[p.id,p.source.fingerprint])))),previousSceneFingerprint:kind==='snapshot'?null:model.sceneFingerprint,target:kind==='snapshot'?null:'A',before:kind==='snapshot'?{}:{PlacementZ:kind==='edit'?0:5},after:kind==='snapshot'?{}:{PlacementZ:z},undoSnapshotId:null,...change};
  const p=join(inbox,snapshotId);await mkdir(p);await writeFile(join(p,'manifest.json'),JSON.stringify(m));await writeFile(join(p,'native.FCStd'),native);for(const x of parts)await writeFile(join(p,x.id+'.json'),mesh);
  return m;
 }
 const request=m=>({documentId:model.documentId,expectedRevision:model.revision,snapshotId:m.snapshotId,mode:m.kind==='snapshot'?'attach':m.kind});
 const apply=async(m,extra={})=>{model=await prepareCadSync({...request(m),...extra},model,comments,revisions,import.meta.dirname,dir,inbox);revisions.set(model.revision,model);};
 try{
  const base=await snapshot(0);await apply(base);assert.equal(model.parts.length,2);assert.equal(model.geometry.parts.A.stepRoundTripValid,false);
  const preview=await readPreview(import.meta.dirname,model,dir);
  const makeComment=id=>{const payload=validateComment({documentId:model.documentId,revision:model.revision,selection:{kind:'object',objectId:id},camera:{position:[1,1,1],target:[0,0,0]},comment:'move A'},model,preview);const c={id:randomUUID(),payload,sha256:hash(id),receipt:null};comments.set(c.id,c);return{commentId:c.id,sha256:c.sha256};};
  const wrong=makeComment('B'),correct=makeComment('A'), edit=await snapshot(5,'edit');
  await assert.rejects(()=>apply(edit,wrong),/评论目标/);
  await assert.rejects(()=>apply(edit,{...correct,expectedRevision:'r1'}),/版本/);
  const tampered=await snapshot(5,'edit');await writeFile(join(inbox,tampered.snapshotId,'A.json'),'{}');await assert.rejects(()=>apply(tampered,correct),/网格哈希/);
  const collateral=await snapshot(5,'edit');collateral.parts[1].color='#ffffff';await writeFile(join(inbox,collateral.snapshotId,'manifest.json'),JSON.stringify(collateral));await assert.rejects(()=>apply(collateral,correct),/非目标/);
  await apply(edit,correct);assert.equal(model.parts[0].properties.PlacementZ,5);assert.equal(model.parts[1].properties.PlacementZ,0);
  const undo=await snapshot(0,'undo',{undoSnapshotId:edit.snapshotId});await assert.rejects(()=>apply(undo,{operationId:'r2'}),/最近/);await apply(undo,{operationId:'r3'});assert.equal(model.sceneFingerprint,base.sceneFingerprint);
 }finally{await rm(dir,{recursive:true,force:true});}
});
