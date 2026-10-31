import type { Model, PlateRequest, PlateUpdate, Comments } from './types.js';
import { validateDocument, validateEditComment } from './model.js';

function validateSpacing(spacing: number, diameter: number, length: number): void {
  function fail(message: string): never { throw Object.assign(new Error(message), {status:400}); }
  if (typeof spacing!=='number' || !Number.isFinite(spacing) || spacing<=0) fail('孔距必须是有限的正数。');
  if (spacing<=diameter) fail('孔距必须大于孔径，双孔不能相交或相切。');
  if (spacing+diameter>=length) fail('两个孔必须完整位于板内，不能接触板边。');
}

export function plateRequest(input: PlateRequest, model: Model): PlateRequest {
  validateDocument(input, model);
  function fail(message: string): never { throw Object.assign(new Error(message), {status:400}); }
  const dimensions = ['lengthMm','widthMm','thicknessMm','holeDiameterMm','holeSpacingMm'] as const;
  const fields = ['documentId','expectedRevision','requestId',...dimensions];
  if (Object.keys(input).some(key=>!fields.includes(key))) fail('创建请求包含未知参数。');
  if (typeof input.requestId !== 'string' || !/^[a-zA-Z0-9_-]{1,128}$/.test(input.requestId)) fail('requestId 无效。');
  if (typeof input.expectedRevision !== 'string' || !/^r[1-9][0-9]*$/.test(input.expectedRevision)) fail('模型版本无效。');
  for (const key of dimensions) {
    if (typeof input[key] !== 'number' || !Number.isFinite(input[key]) || input[key] <= 0) fail('尺寸必须是有限的正数。');
  }
  validateSpacing(input.holeSpacingMm,input.holeDiameterMm,input.lengthMm);
  if (input.holeDiameterMm >= input.widthMm) {
    fail('两个孔必须完整位于板内，不能接触板边。');
  }
  return {documentId:input.documentId,expectedRevision:input.expectedRevision,requestId:input.requestId,lengthMm:input.lengthMm,widthMm:input.widthMm,thicknessMm:input.thicknessMm,holeDiameterMm:input.holeDiameterMm,holeSpacingMm:input.holeSpacingMm};
}

export function preparePlate(request: PlateRequest, model: Model): Model {
  if (request.expectedRevision !== model.revision || model.parts.length !== 0) {
    throw Object.assign(new Error('只能在当前版本的空白文档创建安装板。'), {status:409});
  }
  const next = structuredClone(model);
  next.name = '双孔安装板';
  next.revision = `r${Number(model.revision.slice(1))+1}`;
  next.parts = [{id:'plate-01',name:'双孔安装板',kind:'box',profile:'mounting-plate',
    size:[request.lengthMm,request.widthMm,request.thicknessMm],
    holeDiameter:request.holeDiameterMm,holeSpacing:request.holeSpacingMm,
    position:[0,0,request.thicknessMm/2],color:'#748d92'}];
  next.lastOperation = {type:'create-mounting-plate',objectId:'plate-01',request,
    previousRevision:model.revision,createdAt:new Date().toISOString()};
  delete next.geometry;
  return next;
}

export function preparePlateSpacingUpdate(input: PlateUpdate, model: Model, comments: Comments) {
  const {comment,part}=validateEditComment(input,model,comments);
  function fail(message: string): never {throw Object.assign(new Error(message),{status:400});}
  if (part.kind!=='box' || part.profile!=='mounting-plate') fail('只能修改双孔安装板的对称孔距。');
  const fields=['documentId','expectedRevision','commentId','sha256','holeSpacingMm'];
  if (Object.keys(input).some(key=>!fields.includes(key))) fail('编辑请求包含未知参数。');
  validateSpacing(input.holeSpacingMm,part.holeDiameter,part.size[0]);
  if (input.holeSpacingMm===part.holeSpacing) return {comment,part,next:null};
  const next=structuredClone(model);
  const target=next.parts.find(item=>item.id===part.id);
  if (!target || target.profile!=='mounting-plate') throw new Error('安装板目标已不存在。');
  target.holeSpacing=input.holeSpacingMm;
  next.revision=`r${Number(model.revision.slice(1))+1}`;
  next.lastOperation={type:'update-plate-hole-spacing',objectId:part.id,commentId:comment.id,
    parameters:{holeSpacingMm:input.holeSpacingMm},previousRevision:model.revision,createdAt:new Date().toISOString()};
  delete next.geometry;
  return {comment,part,next};
}
