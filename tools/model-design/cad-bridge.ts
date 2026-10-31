import {prepareAssemblySync} from './assembly-sync.js';
import {z} from 'zod';
import {readFile,realpath,mkdir,writeFile,stat} from 'node:fs/promises';
import {join,resolve} from 'node:path';
import {createHash,randomUUID} from 'node:crypto';
import {runGeometry} from './geometry-store.js';
import {validateDocument,validateEditComment} from './model.js';
import {operationHistory} from './history.js';
import type {Model,Comments,Revisions,CadSyncRequest} from './types.js';
const id=z.string().regex(/^[a-zA-Z0-9_-]{1,128}$/), hash=z.string().regex(/^[a-f0-9]{64}$/);
const numbers=z.record(z.string(),z.number().finite());
const vector=z.tuple([z.number().finite(),z.number().finite(),z.number().finite()]);
const sourceSchema=z.strictObject({application:z.literal('FreeCAD'),documentName:z.string().min(1).max(128),
  documentUid:z.string().uuid(),objectName:z.string().min(1).max(128),fingerprint:hash});
const manifestSchema=z.strictObject({
  schema:z.literal('solidcue-freecad/v1'),snapshotId:id,kind:z.enum(['snapshot','edit','undo']),source:sourceSchema,
  name:z.string().min(1).max(200),unit:z.literal('mm'),upAxis:z.literal('Z'),stepSha256:hash,
  previousFingerprint:hash.nullable(),before:numbers,after:numbers,properties:numbers,
  undoSnapshotId:id.optional(),
  faces:z.array(z.strictObject({id:z.string().regex(/^Face[1-9][0-9]*$/),area:z.number().positive(),
    center:vector,bounds:z.array(z.number().finite()).length(6)})).min(1).max(10000),
});
const requestSchema=z.strictObject({documentId:z.string(),expectedRevision:z.string().regex(/^r[1-9][0-9]*$/),
  snapshotId:id,mode:z.enum(['attach','refresh','edit','undo']),
  commentId:z.string().uuid().optional(),sha256:hash.optional(),operationId:z.string().optional()});
const sameNumbers=(a: Record<string,number>, b: Record<string,number>)=>Object.keys(a).length===Object.keys(b).length && Object.entries(a).every(([key,value])=>b[key]===value);
function conflict(message: string): never {throw Object.assign(new Error(message),{status:409});}
async function readContained(root: string, path: string, limit: number): Promise<Buffer> {
  if(await realpath(path)!==resolve(path) || !(await realpath(path)).startsWith((await realpath(root))+'/')) throw new Error('CAD 快照不能使用符号链接或越界路径。');
  if((await stat(path)).size>limit) throw new Error('CAD 快照文件过大。');
  const bytes=await readFile(path);
  if(bytes.length>limit) throw new Error('CAD 快照文件过大。');
  return bytes;
}
export async function prepareCadSync(input: CadSyncRequest, model: Model, comments: Comments, revisions: Revisions,
  root: string, dataRoot: string, inbox: string): Promise<Model> {
  const request=requestSchema.parse(input);validateDocument(request,model);
  if(request.expectedRevision!==model.revision) conflict('模型版本已变化，请先读取当前状态。');
  const sourceFolder=join(inbox,request.snapshotId);
  const bytes=await readContained(inbox,join(sourceFolder,'manifest.json'),2*1024*1024);
  const raw=JSON.parse(bytes.toString('utf8'));
  if(raw?.schema==='cybertrack-assembly/v1') return prepareAssemblySync(raw,request,model,comments,revisions,dataRoot,inbox);
  const manifest=manifestSchema.parse(raw);
  if(manifest.snapshotId!==request.snapshotId) throw new Error('快照 ID 不匹配。');
  const step=await readContained(inbox,join(sourceFolder,'model.step'),8*1024*1024);
  if(createHash('sha256').update(step).digest('hex')!==manifest.stepSha256) throw new Error('STEP 哈希不匹配，未发布。');
  const part=model.parts[0];
  if(request.mode==='attach') {
    if(model.parts.length || manifest.kind!=='snapshot') conflict('只能在空白文档连接初始 CAD 快照。');
  } else {
    if(part?.kind!=='step' || part.source.documentUid!==manifest.source.documentUid ||
       part.source.objectName!==manifest.source.objectName || part.source.documentName!==manifest.source.documentName) conflict('CAD 来源文档或对象不匹配。');
    if(request.mode==='refresh') {
      if(manifest.kind!=='snapshot') throw new Error('刷新需要只读导出的快照。');
    } else {
      if(manifest.previousFingerprint!==part.source.fingerprint) conflict('CAD 修改基线不匹配，请同步原生文档后重新选择。');
      const keys=Object.keys(manifest.before);
      if(!keys.length || keys.length!==Object.keys(manifest.after).length ||
         keys.some(key=>part.properties[key]!==manifest.before[key] || manifest.properties[key]!==manifest.after[key]) ||
         !sameNumbers({...part.properties,...manifest.after},manifest.properties)) conflict('原生属性变化与快照基线不一致。');
      if(request.mode==='edit') {
        if(manifest.kind!=='edit' || !request.commentId || !request.sha256) throw new Error('修改同步需要真实评论 ID/hash 和编辑快照。');
        validateEditComment({...request,commentId:request.commentId,sha256:request.sha256},model,comments);
      } else {
        const history=operationHistory(revisions), op=model.lastOperation;
        if(manifest.kind!=='undo' || !request.operationId || history.undoOperationId!==request.operationId ||
           op?.type!=='sync-cad' || op.mode!=='edit' || manifest.undoSnapshotId!==op.snapshotId) conflict('只能恢复最近且未被外部修改的 CAD 编辑。');
        if(!sameNumbers(manifest.after,op.before)) conflict('CAD 恢复属性不匹配。');
      }
    }
    if(manifest.source.fingerprint===part.source.fingerprint) conflict('原生文档没有变化，无需发布新版本。');
  }
  // Freeze input bytes before the kernel runs, avoiding races with an exporting process.
  const frozen=join(dataRoot,'cad-inputs',randomUUID());await mkdir(frozen,{recursive:true});
  await writeFile(join(frozen,'manifest.json'),bytes,{flag:'wx'});
  await writeFile(join(frozen,'model.step'),step,{flag:'wx'});
  const next: Model={documentId:model.documentId,revision:'r'+(Number(model.revision.slice(1))+1),
    unit:'mm',upAxis:'Z',name:manifest.name,cadSnapshotId:manifest.snapshotId,
    parts:[{id:'external-01',name:manifest.name,kind:'step',position:[0,0,0],color:'#889e96',
      source:manifest.source,properties:manifest.properties}]};
  if(request.mode==='undo') {
    const target=revisions.get(request.operationId!)!;
    next.lastOperation={type:'undo',objectId:'external-01',previousRevision:model.revision,
      createdAt:new Date().toISOString(),undoOf:request.operationId!,restoredRevision:target.lastOperation!.previousRevision,
      snapshotId:manifest.snapshotId};
  } else {
    next.lastOperation={type:'sync-cad',objectId:'external-01',previousRevision:model.revision,
      createdAt:new Date().toISOString(),snapshotId:manifest.snapshotId,mode:request.mode,
      ...(request.mode==='edit' ? {commentId:request.commentId} : {}),before:manifest.before,after:manifest.after};
  }
  let restoreStep: string | undefined;
  if(request.mode==='undo') {
    const original=revisions.get(revisions.get(request.operationId!)!.lastOperation!.previousRevision)!;
    const originalPart=original.parts[0];
    if(originalPart?.kind!=='step' || !sameNumbers(manifest.properties,originalPart.properties)) conflict('恢复后的原生属性与原版本不一致。');
    restoreStep=join(dataRoot,'geometry',original.geometry!.key,'external-01.step');
  }
  next.geometry=await runGeometry(root,next.revision,dataRoot,'step_preview.py',{source:frozen,restoreStep});
  return next;
}
