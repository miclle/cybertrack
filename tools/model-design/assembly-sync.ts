// CyberTrack extension: publish native assembly previews without claiming STEP validation.
import {z} from 'zod';
import {createHash,randomUUID} from 'node:crypto';
import {join,resolve} from 'node:path';
import {readFile,realpath,stat,mkdir,writeFile} from 'node:fs/promises';
import {validateEditComment} from './model.js';
import {operationHistory} from './history.js';
import type {Model,Comments,Revisions,CadSyncRequest,Preview} from './types.js';
const id=z.string().regex(/^[a-zA-Z0-9_-]{1,128}$/), hash=z.string().regex(/^[a-f0-9]{64}$/);
const vector=z.tuple([z.number().finite(),z.number().finite(),z.number().finite()]);
const properties=z.strictObject({PlacementX:z.number().finite(),PlacementY:z.number().finite(),PlacementZ:z.number().finite()});
const delta=properties.partial();
const geometry=z.strictObject({valid:z.boolean(),solids:z.number().int().nonnegative(),volumeMm3:z.number().finite(),
  faces:z.number().int().positive(),boundsMm:z.array(z.number().finite()).length(6),stepRoundTripValid:z.literal(false),stepBoundsVerified:z.literal(false)});
const partSchema=z.strictObject({id,name:z.string().min(1).max(200),kind:z.literal('native'),position:vector,color:z.string().regex(/^#[a-fA-F0-9]{6}$/),
  source:z.strictObject({application:z.literal('FreeCAD'),documentName:id,documentUid:z.string().uuid(),objectName:id,fingerprint:hash}),
  properties,meshSha256:hash,geometry});
const manifestSchema=z.strictObject({schema:z.literal('cybertrack-assembly/v1'),snapshotId:id,kind:z.enum(['snapshot','edit','undo']),
  name:z.string().min(1).max(200),unit:z.literal('mm'),upAxis:z.literal('Z'),parts:z.array(partSchema).min(1).max(500),
  nativeSha256:hash,sceneFingerprint:hash,previousSceneFingerprint:hash.nullable(),target:id.nullable(),
  before:delta,after:delta,undoSnapshotId:id.nullable()});
const meshSchema=z.strictObject({positions:z.array(z.number().finite()).min(9).max(9000000),
  indices:z.array(z.number().int().nonnegative()).min(3).max(3000000),
  faces:z.array(z.strictObject({id:z.string().regex(/^Face[1-9][0-9]*$/),type:z.literal('native'),start:z.number().int().nonnegative(),count:z.number().int().nonnegative()})).min(1).max(100000)});
const digest=(b:Buffer|string)=>createHash('sha256').update(b).digest('hex');
const same=(a:unknown,b:unknown)=>JSON.stringify(a)===JSON.stringify(b);
function reject(message:string):never {throw Object.assign(new Error(message),{status:409});}
async function contained(root:string,path:string,limit:number){
  if(await realpath(path)!==resolve(path) || !(await realpath(path)).startsWith((await realpath(root))+'/'))throw new Error('快照路径越界或包含符号链接');
  if((await stat(path)).size>limit)throw new Error('快照文件过大');
  const bytes=await readFile(path);if(bytes.length>limit)throw new Error('快照文件过大');return bytes;
}
export async function prepareAssemblySync(raw:unknown,request:CadSyncRequest,model:Model,comments:Comments,revisions:Revisions,dataRoot:string,inbox:string):Promise<Model>{
  const m=manifestSchema.parse(raw), folder=join(inbox,request.snapshotId);
  if(m.snapshotId!==request.snapshotId)reject('快照 ID 不匹配');
  const ids=m.parts.map(p=>p.id);
  if(new Set(ids).size!==ids.length)reject('零件 ID 重复');
  const identity=m.parts[0].source;
  for(const p of m.parts)if(p.id!==p.source.objectName || p.source.documentUid!==identity.documentUid || p.source.documentName!==identity.documentName || p.position.some(v=>v!==0))reject('装配来源或坐标不一致');
  const fingerprints=Object.fromEntries([...m.parts].sort((a,b)=>a.id.localeCompare(b.id,'en')).map(p=>[p.id,p.source.fingerprint]));
  // Python uses code-point order; sort keys explicitly without locale-dependent collation.
  const canonical=Object.fromEntries(Object.keys(fingerprints).sort().map(k=>[k,fingerprints[k]]));
  if(digest(JSON.stringify(canonical))!==m.sceneFingerprint)reject('装配指纹不匹配');
  if(request.mode==='attach'){
    if(model.parts.length || m.kind!=='snapshot')reject('整机初始快照需要空白文档');
  }else{
    if(!model.sceneFingerprint || model.parts.length!==m.parts.length || model.parts.some(p=>p.kind!=='native' || !ids.includes(p.id) || p.source.documentUid!==identity.documentUid || p.source.documentName!==identity.documentName))reject('整机来源或零件集合变化');
    if(request.mode==='refresh'){
      if(m.kind!=='snapshot')reject('刷新需要只读快照');
    }else{
      if(m.previousSceneFingerprint!==model.sceneFingerprint)reject('整机修改基线已变化');
      const changed=m.parts.filter(p=>model.parts.find(old=>old.id===p.id && old.kind==='native' && old.source.fingerprint===p.source.fingerprint)===undefined);
      if(changed.length!==1 || changed[0].id!==m.target)reject('一次修改只能影响评论目标零件');
      const old=model.parts.find(p=>p.id===m.target), next=changed[0];
      if(old?.kind!=='native' || !next.geometry.valid)reject('目标不是有效原生零件');
      const keys=Object.keys(m.before) as (keyof typeof m.before)[];
      if(!keys.length || !same(keys.sort(),Object.keys(m.after).sort()) || keys.some(k=>old.properties[k]!==m.before[k] || next.properties[k]!==m.after[k]) || !same({...old.properties,...m.after},next.properties))reject('坐标变化与基线不一致');
      for(const p of m.parts)if(p.id!==m.target){
        const old=model.parts.find(x=>x.id===p.id);
        if(old?.kind!=='native' || old.meshSha256!==p.meshSha256 || !same(old.properties,p.properties) || old.color!==p.color || old.name!==p.name)reject('非目标零件被修改');
      }
      if(request.mode==='edit'){
        if(m.kind!=='edit' || !request.commentId || !request.sha256)reject('需要评论 ID/hash');
        const {part}=validateEditComment({...request,commentId:request.commentId,sha256:request.sha256},model,comments);
        if(part.id!==m.target)reject('评论目标与修改对象不一致');
      }else{
        const op=model.lastOperation;
        if(m.kind!=='undo' || operationHistory(revisions).undoOperationId!==request.operationId || op?.type!=='sync-cad' || op.mode!=='edit' || m.undoSnapshotId!==op.snapshotId)reject('只能恢复最近一次原生修改');
        const original=revisions.get(op.previousRevision);
        if(original?.sceneFingerprint!==m.sceneFingerprint)reject('原生整机未恢复到原始几何指纹');
      }
    }
    if(model.sceneFingerprint===m.sceneFingerprint)reject('整机没有变化');
  }
  const native=await contained(inbox,join(folder,'native.FCStd'),128*1024*1024);
  if(digest(native)!==m.nativeSha256)reject('FCStd 哈希不匹配');
  const revision='r'+(Number(model.revision.slice(1))+1), key=revision+'-'+randomUUID();
  const preview:Preview={revision,engine:'FreeCAD native assembly tessellation',parts:{},meshes:{}};
  let total=0;
  for(const part of m.parts){
    const bytes=await contained(inbox,join(folder,part.id+'.json'),64*1024*1024);total+=bytes.length;
    if(total>128*1024*1024)reject('整机预览超过 128 MiB');
    if(digest(bytes)!==part.meshSha256)reject('网格哈希不匹配');
    const mesh=meshSchema.parse(JSON.parse(bytes.toString('utf8')));
    if(mesh.positions.length%3 || mesh.indices.length%3 || mesh.indices.some(i=>i>=mesh.positions.length/3))reject('网格索引无效');
    let cursor=0;const faces=new Set<string>();
    for(const f of mesh.faces){if(f.start!==cursor || faces.has(f.id))reject('面映射无效');cursor+=f.count;faces.add(f.id);}
    if(cursor!==mesh.indices.length/3 || mesh.faces.length!==part.geometry.faces)reject('面映射不完整');
    preview.parts[part.id]=part.geometry;preview.meshes[part.id]=mesh;
  }
  const output=join(dataRoot,'geometry',key);await mkdir(output,{recursive:true});
  await writeFile(join(output,'preview.json'),JSON.stringify(preview),{flag:'wx'});
  await writeFile(join(output,'native.FCStd'),native,{flag:'wx'});
  const next:Model={documentId:model.documentId,revision,unit:'mm',upAxis:'Z',name:m.name,cadSnapshotId:m.snapshotId,
    sceneFingerprint:m.sceneFingerprint,parts:m.parts.map(({geometry,...part})=>part),geometry:{revision,engine:preview.engine,parts:preview.parts,key}};
  next.lastOperation=request.mode==='undo' ? {type:'undo',objectId:m.target!,previousRevision:model.revision,createdAt:new Date().toISOString(),undoOf:request.operationId!,restoredRevision:revisions.get(request.operationId!)!.lastOperation!.previousRevision,snapshotId:m.snapshotId} :
    {type:'sync-cad',objectId:m.target ?? m.parts[0].id,previousRevision:model.revision,createdAt:new Date().toISOString(),snapshotId:m.snapshotId,mode:request.mode,...(request.mode==='edit'?{commentId:request.commentId}:{}),before:m.before,after:m.after};
  return next;
}
