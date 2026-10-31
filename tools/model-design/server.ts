import {gzipSync} from 'node:zlib';
import type { IncomingMessage } from 'node:http';
import type { Model, Comments, Revisions, JournalEvent, CommentRecord, Processing, SpacerUpdate, PlateUpdate, HoleRequest, UndoRequest, StepRequest, CadSyncRequest } from './types.js';
import { errorMessage, errorCode, errorStatus } from './errors.js';
import http from 'node:http';
import { operationHistory, prepareUndo } from './history.js';
import { buildGeometry, readPreview, validateHoleRequest, requireGeometry } from './geometry-store.js';
import { queueComment } from './delivery.js';
import { readFile, mkdir, appendFile } from 'node:fs/promises';
import { dirname, join, extname, resolve } from 'node:path';
import { homedir } from 'node:os';
import { fileURLToPath } from 'node:url';
import { randomUUID, createHash } from 'node:crypto';
import { model as seedModel, blankModel, validateComment } from './model.js';
import { spacerRequest, prepareSpacer, prepareSpacerUpdate } from './spacer.js';
import { plateRequest, preparePlate, preparePlateSpacingUpdate } from './plate.js';
import { prepareCadSync } from './cad-bridge.js';
import { stepCatalog, exportStep, saveStep } from './step-export.js';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const dataRoot = process.env.CAD_COMMENT_DATA_DIR || join(root, '.data');
const exportRoot = resolve(process.env.CAD_COMMENT_EXPORT_DIR || join(homedir(),'Downloads','SolidCue'));
const cadInbox = resolve(process.env.CAD_COMMENT_CAD_INBOX || join(dataRoot,'cad-inbox'));
const port = Number(process.env.CAD_COMMENT_PORT || 9473);
const origin = `http://127.0.0.1:${port}`;
await mkdir(dataRoot, { recursive: true });
const journal = join(dataRoot, 'events.jsonl');
const comments: Comments = new Map();
let model: Model = structuredClone(seedModel);
const revisions: Revisions = new Map();
let editing = false;
let packedPreview: {key:string;data:string}|undefined;
const threadId = process.env.CAD_CHAT_THREAD_ID || process.env.CODEX_THREAD_ID;
const inFlight = new Set<string>();
try {
  for (const line of (await readFile(journal, 'utf8')).split('\n').filter(Boolean)) {
    const event = JSON.parse(line) as JournalEvent;
    if (event.type === 'geometry-model') {
      model=event.model; revisions.set(model.revision,model);
      const op=model.lastOperation;
      const record = op && 'commentId' in op && op.commentId ? comments.get(op.commentId) : undefined;
      if (record) record.processing = {status:'completed', revision:model.revision};
    }
    if (event.type === 'comment') comments.set(event.record.id, event.record);
    if (event.type === 'delivery') { const record=comments.get(event.id); if (record) record.delivery=event.delivery; }
    if (event.type === 'processing') { const record=comments.get(event.id); if (record) record.processing=event.processing; }
    if (event.type === 'receipt') { const record=comments.get(event.id); if (record) record.receipt=event.receipt; }
  }
} catch (error) { if (errorCode(error) !== 'ENOENT') throw error; }
async function log(event: JournalEvent): Promise<void> { await appendFile(journal, JSON.stringify(event) + '\n'); }
async function processing(record: CommentRecord, status: Processing['status'], message: string, details: Pick<Processing, 'revision' | 'changed'> = {}): Promise<void> {
  const value: Processing = {status, message, ...details, updatedAt:new Date().toISOString()};
  await log({type:'processing',id:record.id,processing:value}); record.processing=value;
}
for (const record of comments.values()) {
  if (record.processing?.status === 'processing') await processing(record,'failed','服务中断，编辑未提交。');
}
if (!model.geometry) {
  const initial = process.env.CAD_COMMENT_INITIAL_MODEL || 'demo';
  if (!['demo','blank'].includes(initial)) throw new Error('CAD_COMMENT_INITIAL_MODEL 必须为 demo 或 blank。');
  if (initial === 'blank') {
    if (comments.size) throw new Error('已有评论的日志不能初始化为空白文档。');
    model=blankModel(`solidcue-${randomUUID()}`);
  }
  model.geometry=await buildGeometry(root,model,dataRoot);
  await log({type:'geometry-model',model}); revisions.set(model.revision,model);
}
let preview = await readPreview(root,model,dataRoot);
const mime: Record<string,string> = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css' };
const allowed = new Map([['/', 'index.html'], ['/app.js', 'dist/web/app.js'], ['/style.css', 'style.css']]);
// Type annotations do not validate JSON; each handler retains its runtime checks.
async function body<T>(req: IncomingMessage): Promise<T> {
  if (!req.headers['content-type']?.startsWith('application/json')) throw new Error('需要 JSON 请求。');
  let text = '';
  for await (const chunk of req) { text += chunk; if (text.length > 16000) throw new Error('请求过大。'); }
  return JSON.parse(text);
}
const server = http.createServer(async (req, res) => {
  const json = (status: number, value: unknown) => { res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' }); res.end(JSON.stringify(value)); };
  if (req.headers.host !== `127.0.0.1:${port}` || (req.headers.origin && req.headers.origin !== origin)) return json(403, { error: '仅接受本机同源请求。' });
  const url = new URL(req.url || '/', origin);
  try {
    if (req.method === 'GET' && url.pathname === '/api/state') {
      let previewFields: object={preview};
      if(url.searchParams.get('preview')==='gzip') {
        const key=requireGeometry(model).key;
        if(url.searchParams.get('geometryKey')===key) previewFields={previewUnchanged:true};
        else {
          if(packedPreview?.key!==key) packedPreview={key,data:gzipSync(JSON.stringify(preview)).toString('base64')};
          previewFields={previewCompressed:{encoding:'gzip-base64',data:packedPreview.data}};
        }
      }
      return json(200, { model, ...previewFields, history: operationHistory(revisions), editing, revisions: [...revisions.keys()], stepExports: stepCatalog(revisions), comments: [...comments.values()], cadBridge: {adapterScript:join(root,'freecad_bridge.py'),assemblyAdapterScript:join(root,'assembly_bridge.py'),inbox:cadInbox}, transport: threadId ? 'codex-cli-queue' : 'agent-pull', targetThreadId: threadId || null, nativeMessageBridge: false });
    }
    if (req.method === 'POST' && url.pathname === '/api/cad/sync') {
      const input=await body<CadSyncRequest>(req);
      if(editing) return json(409,{error:'模型正在更新，请稍后重试。'});
      editing=true;
      try {
        const next=await prepareCadSync(input,model,comments,revisions,root,dataRoot,cadInbox);
        const nextPreview=await readPreview(root,next,dataRoot);
        await log({type:'geometry-model',model:next});
        model=next;preview=nextPreview;revisions.set(model.revision,model);
        if(input.mode==='edit' && input.commentId) {
          const comment=comments.get(input.commentId);
          if(comment) comment.processing={status:'completed',revision:model.revision};
        }
        return json(200,{revision:model.revision,source:model.parts.find(p=>p.id===model.lastOperation?.objectId) ?? model.parts[0],snapshotId:model.cadSnapshotId});
      } finally {editing=false;}
    }
    if (req.method === 'POST' && url.pathname === '/api/export-step') return json(200, await exportStep(await body(req), model, revisions, dataRoot));
    if (req.method === 'POST' && url.pathname === '/api/save-step') return json(200, await saveStep(await body(req), model, revisions, dataRoot, exportRoot));
    if (req.method === 'GET' && url.pathname === '/api/download-step') {
      const artifact = await exportStep(Object.fromEntries(url.searchParams) as unknown as StepRequest, model, revisions, dataRoot);
      res.once('finish', () => console.info(JSON.stringify({
        event:'step-download-response', revision:artifact.revision, partId:artifact.partId,
        byteLength:artifact.byteLength, sha256:artifact.sha256, at:new Date().toISOString(),
      })));
      res.writeHead(200, {
        'Content-Type':'application/step', 'Cache-Control':'no-store', 'X-Content-Type-Options':'nosniff',
        'Content-Disposition':`attachment; filename="${artifact.filename}"`,
        'Content-Length':artifact.byteLength,
      });
      return res.end(Buffer.from(artifact.resource.blob,'base64'));
    }
    if (req.method === 'POST' && ['/api/geometry/spacer','/api/geometry/mounting-plate'].includes(url.pathname)) {
      const plate=url.pathname==='/api/geometry/mounting-plate';
      const request=(plate ? plateRequest : spacerRequest)(await body(req),model);
      const prior=[...revisions.values()].find(version=>version.lastOperation && 'request' in version.lastOperation && version.lastOperation.request.requestId===request.requestId);
      if (prior) {
        if (JSON.stringify((prior.lastOperation && 'request' in prior.lastOperation ? prior.lastOperation.request : undefined))!==JSON.stringify(request)) return json(409,{error:'requestId 已用于不同的创建请求。'});
        const entry=operationHistory(revisions).entries.find(item=>item.id===prior.revision);
        return json(200,{revision:prior.revision,currentRevision:model.revision,operation:prior.lastOperation,
          operationId:prior.revision,status:entry?.status,replayed:true,geometry:requireGeometry(prior).parts[prior.lastOperation!.objectId]});
      }
      if (editing) return json(409,{error:'模型正在更新，请稍后重试。'});
      const next='lengthMm' in request ? preparePlate(request,model) : prepareSpacer(request,model);
      editing=true;
      try {
        next.geometry=await buildGeometry(root,next,dataRoot);
        const nextPreview=await readPreview(root,next,dataRoot);
        await log({type:'geometry-model',model:next});
        model=next; preview=nextPreview; revisions.set(model.revision,model);
        return json(201,{revision:model.revision,currentRevision:model.revision,operationId:model.revision,
          operation:model.lastOperation,status:'applied',replayed:false,geometry:requireGeometry(model).parts[model.lastOperation!.objectId]});
      } finally {editing=false;}
    }
    if (req.method === 'POST' && ['/api/geometry/spacer-parameters','/api/geometry/plate-hole-spacing'].includes(url.pathname)) {
      const plate=url.pathname==='/api/geometry/plate-hole-spacing';
      const input=await body<SpacerUpdate & PlateUpdate>(req);
      if (editing) return json(409,{error:'模型正在更新，请稍后重试。'});
      let validated;
      try {validated=(plate ? preparePlateSpacingUpdate : prepareSpacerUpdate)(input,model,comments);} catch(error) {
        const record=comments.get(input?.commentId);
        if (record && record.sha256===input.sha256 && input.documentId===model.documentId && record.processing?.status!=='completed') await processing(record,'failed',errorMessage(error));
        throw error;
      }
      const {comment,part,next}=validated;
      editing=true;
      try {
        if (!next) {
          await processing(comment,'completed','尺寸与当前模型一致，无需修改。',{revision:model.revision,changed:false});
          return json(200,{revision:model.revision,changed:false,geometry:requireGeometry(model).parts[part.id]});
        }
        await processing(comment,'processing',plate ? '正在对称调整双孔中心距，保持板尺寸、孔径与底面不变，并验证实体及 STEP。' : '正在更新垫套尺寸，保持底面 Z=0，并验证实体及 STEP。');
        next.geometry=await buildGeometry(root,next,dataRoot);
        const nextPreview=await readPreview(root,next,dataRoot);
        await log({type:'geometry-model',model:next});
        model=next;preview=nextPreview;revisions.set(model.revision,model);
        comment.processing={status:'completed',revision:model.revision};
        return json(200,{revision:model.revision,changed:true,operation:model.lastOperation,geometry:requireGeometry(model).parts[part.id]});
      } catch(error) {
        await processing(comment,'failed',errorMessage(error));throw error;
      } finally {editing=false;}
    }
    if (req.method === 'POST' && url.pathname === '/api/geometry/center-hole') {
      if (editing) return json(409,{error:'模型正在更新，请稍后重试。'});
      const input=await body<HoleRequest>(req);
      if (editing) return json(409,{error:'模型正在更新，请稍后重试。'});
      let validated;
      try { validated=validateHoleRequest(input,model,comments); } catch(error) {
        const record=comments.get(input.commentId);
        if(record && record.sha256===input.sha256 && record.processing?.status!=='completed') await processing(record,'failed',errorMessage(error));
        throw error;
      }
      const {comment,part}=validated;
      editing=true;
      try {
        await processing(comment,'processing','正在计算实体并验证 STEP。');
        const next=structuredClone(model); const prior=model.revision;
        next.revision=`r${Number(model.revision.slice(1))+1}`;
        const target=next.parts.find(p=>p.id===part.id);
        if (!target || target.kind!=='cylinder') throw new Error('圆柱目标已不存在。');
        target.centerHoleDiameter=input.diameterMm;
        next.lastOperation={type:'center-through-hole',commentId:comment.id,objectId:part.id,diameterMm:input.diameterMm,previousRevision:prior,createdAt:new Date().toISOString()};
        delete next.geometry;
        next.geometry=await buildGeometry(root,next,dataRoot);
        const nextPreview=await readPreview(root,next,dataRoot);
        await log({type:'geometry-model',model:next});
        model=next; preview=nextPreview; revisions.set(model.revision,model);
        comment.processing={status:'completed',revision:model.revision};
        return json(200,{revision:model.revision,operation:model.lastOperation,geometry:requireGeometry(model).parts[part.id],stepUrl:`${origin}/api/geometry/${model.revision}/${part.id}.step`});
      } catch(error) {
        await processing(comment,'failed',errorMessage(error)); throw error;
      } finally {editing=false;}
    }
    if (req.method === 'POST' && url.pathname === '/api/geometry/undo') {
      const input = await body<UndoRequest>(req);
      if (editing) return json(409,{error:'模型正在更新，请稍后重试。'});
      const next = prepareUndo(input,model,revisions);
      editing=true;
      try {
        next.geometry=await buildGeometry(root,next,dataRoot);
        const nextPreview=await readPreview(root,next,dataRoot);
        await log({type:'geometry-model',model:next});
        model=next; preview=nextPreview; revisions.set(model.revision,model);
        return json(200,{revision:model.revision,operation:model.lastOperation,history:operationHistory(revisions)});
      } finally {editing=false;}
    }
    const artifact=url.pathname.match(/^\/api\/geometry\/(r[1-9][0-9]*)\/([a-zA-Z0-9_-]+)\.step$/);
    if(req.method==='GET' && artifact) {
      const version=revisions.get(artifact[1]);
      if(!version)return json(404,{error:'模型版本不存在。'});
      if(!version.parts.length || (artifact[2]!=='assembly' && !version.parts.some(part=>part.id===artifact[2]))) return json(404,{error:'该版本没有此 STEP 产物。'});
      const bytes=await readFile(join(dataRoot,'geometry',requireGeometry(version).key,artifact[2]+'.step'));
      res.writeHead(200,{'Content-Type':'application/step','Content-Disposition':`attachment; filename="${artifact[2]}-${artifact[1]}.step"`});return res.end(bytes);
    }
    if (req.method === 'POST' && url.pathname === '/api/comments') {
      const payload = validateComment(await body(req),model,preview);
      const record: CommentRecord = { id: randomUUID(), createdAt: new Date().toISOString(), payload, sha256: createHash('sha256').update(JSON.stringify(payload)).digest('hex'), receipt: null };
      await log({ type: 'comment', record }); comments.set(record.id, record);
      return json(201, record);
    }
    if (req.method === 'POST' && url.pathname === '/api/send') {
      if (req.headers.origin !== origin) return json(403, { error: '发送只接受本机页面的同源操作。' });
      const input = await body<{id:string;sha256:string;message?:string}>(req); const record = comments.get(input.id);
      if (!record || input.sha256 !== record.sha256) return json(409, { error: '评论 ID 或校验值不匹配。' });
      if (record.delivery?.status === 'queued') return json(200, record.delivery);
      if (inFlight.has(record.id) || record.delivery?.status === 'uncertain') return json(409, { error: '投递正在进行或结果不明确，请先核对对话，避免重复发送。' });
      inFlight.add(record.id);
      try {
        record.delivery = { status: 'uncertain', attemptedAt: new Date().toISOString() };
        await log({ type: 'delivery', id: record.id, delivery: record.delivery });
        const delivery = await queueComment(record, threadId);
        await log({ type: 'delivery', id: record.id, delivery }); record.delivery = delivery;
        return json(200, delivery);
      } finally { inFlight.delete(record.id); }
    }
    if (req.method === 'POST' && url.pathname === '/api/receipt') {
      const input = await body<{id:string;sha256:string;message?:string}>(req); const record = comments.get(input.id);
      if (!record || input.sha256 !== record.sha256) return json(409, { error: '评论 ID 或校验值不匹配。' });
      if (typeof input.message !== 'string' || !input.message.trim() || input.message.length > 1500) throw new Error('回执内容无效。');
      const receipt = { receivedAt: new Date().toISOString(), message: input.message.trim(), receiver: 'current-conversation-agent' };
      await log({ type: 'receipt', id: record.id, receipt }); record.receipt = receipt;
      return json(200, { id: record.id, receipt });
    }
    if (req.method === 'GET' && allowed.has(url.pathname)) {
      const file = allowed.get(url.pathname)!;
      const bytes = await readFile(join(root, file));
      res.writeHead(200, { 'Content-Type': mime[extname(file)], 'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff', 'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" });
      return res.end(bytes);
    }
    return json(404, { error: 'Not found' });
  } catch (error) { json(errorStatus(error), { error: errorMessage(error) }); }
});
server.listen(port, '127.0.0.1', () => console.log(`SolidCue: ${origin}\nIndependent directory: ${root}`));
