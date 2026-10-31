import type { Model, SpacerRequest, SpacerUpdate, Comments } from './types.js';
import { validateDocument, validateEditComment } from './model.js';

// The persisted request is also the idempotency identity, including its original revision.
export function spacerRequest(input: SpacerRequest, model: Model): SpacerRequest {
  validateDocument(input, model);
  function fail(message: string): never { throw Object.assign(new Error(message), {status:400}); }
  const fields = ['documentId','expectedRevision','requestId','outerDiameterMm','holeDiameterMm','heightMm'];
  if (Object.keys(input).some(key => !fields.includes(key))) fail('创建请求包含未知参数。');
  if (typeof input.requestId !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(input.requestId)) fail('requestId 无效。');
  if (typeof input.expectedRevision !== 'string' || !/^r[1-9][0-9]*$/.test(input.expectedRevision)) fail('模型版本无效。');
  for (const key of ['outerDiameterMm','holeDiameterMm','heightMm'] as const) {
    if (typeof input[key] !== 'number' || !Number.isFinite(input[key]) || input[key] <= 0) fail('尺寸必须是有限的正数。');
  }
  if (input.holeDiameterMm >= input.outerDiameterMm) fail('孔径必须小于外径。');
  return {documentId:input.documentId,expectedRevision:input.expectedRevision,requestId:input.requestId,outerDiameterMm:input.outerDiameterMm,holeDiameterMm:input.holeDiameterMm,heightMm:input.heightMm};
}

export function prepareSpacer(request: SpacerRequest, model: Model): Model {
  if (request.expectedRevision !== model.revision || model.parts.length !== 0) {
    throw Object.assign(new Error('只能在当前版本的空白文档创建垫套。'), {status:409});
  }
  const next = structuredClone(model);
  next.name = '隔离垫套';
  next.revision = `r${Number(model.revision.slice(1))+1}`;
  next.parts = [{id:'spacer-01',name:'隔离垫套',kind:'cylinder',profile:'spacer',
    radius:request.outerDiameterMm/2,centerHoleDiameter:request.holeDiameterMm,
    height:request.heightMm,position:[0,0,request.heightMm/2],color:'#c0c9ca'}];
  next.lastOperation = {type:'create-spacer',objectId:'spacer-01',request,
    previousRevision:model.revision,createdAt:new Date().toISOString()};
  delete next.geometry;
  return next;
}

export function prepareSpacerUpdate(input: SpacerUpdate, model: Model, comments: Comments) {
  const {comment,part}=validateEditComment(input,model,comments);
  function fail(message: string): never {throw Object.assign(new Error(message),{status:400});}
  if (part.kind!=='cylinder' || part.profile!=='spacer') fail('只能修改隔离垫套的尺寸。');
  const dimensions=['outerDiameterMm','holeDiameterMm','heightMm'] as const;
  const fields=['documentId','expectedRevision','commentId','sha256',...dimensions];
  if (Object.keys(input).some(key=>!fields.includes(key))) fail('编辑请求包含未知参数。');
  const supplied=dimensions.filter(key=>Object.hasOwn(input,key));
  if (!supplied.length) fail('至少需要一个尺寸参数。');
  for (const key of supplied) {
    const value=input[key];
    if (typeof value!=='number' || !Number.isFinite(value) || value<=0) fail('尺寸必须是有限的正数。');
  }
  const outer=input.outerDiameterMm ?? part.radius*2;
  const hole=input.holeDiameterMm ?? part.centerHoleDiameter;
  const height=input.heightMm ?? part.height;
  if (hole>=outer) fail('孔径必须小于外径。');
  if (outer===part.radius*2 && hole===part.centerHoleDiameter && height===part.height) return {comment,part,next:null};
  const next=structuredClone(model);
  const target=next.parts.find(item=>item.id===part.id);
  if (!target || target.profile!=='spacer') throw new Error('垫套目标已不存在。');
  Object.assign(target, {
    radius:outer/2,centerHoleDiameter:hole,height,position:[0,0,height/2],
  });
  next.revision=`r${Number(model.revision.slice(1))+1}`;
  next.lastOperation={type:'update-spacer-parameters',objectId:part.id,commentId:comment.id,
    parameters:Object.fromEntries(supplied.map(key=>[key,input[key]])),
    previousRevision:model.revision,createdAt:new Date().toISOString()};
  delete next.geometry;
  return {comment,part,next};
}
