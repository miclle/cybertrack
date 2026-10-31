import type { Model, CommentInput, CommentPayload, Comments, Vector3, EditRequest, Selection, Preview } from './types.js';
import { fail } from './errors.js';

export const model: Model = {
  documentId: 'cad-comment-demo', revision: 'r1', unit: 'mm', upAxis: 'Z',
  name: '定位夹具 · 交互样件',
  parts: [
    { id: 'base-01', name: '底板', kind: 'box', size: [120, 80, 8], position: [0, 0, 4], color: '#748d92' },
    { id: 'back-01', name: '背板', kind: 'box', size: [120, 8, 70], position: [0, -36, 43], color: '#91a5a8' },
    { id: 'pin-01', name: '定位柱', kind: 'cylinder', radius: 12, height: 30, position: [-30, 0, 23], color: '#c0c9ca' },
    { id: 'knob-01', name: '压紧旋钮', kind: 'cylinder', radius: 18, height: 12, position: [30, 6, 14], color: '#c66c43' },
  ],
};

export function blankModel(documentId: string): Model {
  return {documentId, revision:'r1', unit:'mm', upAxis:'Z', name:'空白文档', parts:[]};
}

export function validateDocument(input: unknown, currentModel: Model): asserts input is Record<string, unknown> & { documentId: string } {
  if (!input || typeof input!=='object' || !('documentId' in input) || input.documentId !== currentModel.documentId) {
    throw Object.assign(new Error('文档不匹配，请打开当前文档卡片。'), {status:409});
  }
}

export function validateEditComment(input: EditRequest, model: Model, comments: Comments) {
  validateDocument(input, model);
  const conflict = (message: string): never => fail(message,409);
  if (input.expectedRevision !== model.revision) conflict('模型版本已变化，请重新点选。');
  const comment = comments.get(input.commentId);
  if (!comment || input.sha256 !== comment.sha256) return conflict('评论 ID 或校验值不匹配。');
  if (comment.payload.documentId !== model.documentId) conflict('评论文档不匹配。');
  if (comment.payload.revision !== model.revision) conflict('这条评论针对旧版本，请重新点选。');
  if (comment.processing?.status === 'completed' || (model.lastOperation && 'commentId' in model.lastOperation && model.lastOperation.commentId === comment.id)) conflict('这条评论已经应用。');
  const part = model.parts.find(part => part.id === comment.payload.selection.objectId);
  if (!part) return conflict('评论目标已不存在，请重新点选。');
  return {comment, part};
}

const vector = (value: unknown): value is Vector3 => Array.isArray(value) && value.length === 3 && value.every(x => typeof x === 'number' && Number.isFinite(x) && Math.abs(x) < 1e7);
export function validateComment(input: CommentInput, currentModel: Model = model, preview?: Preview): CommentPayload {
  if (!input || input.documentId !== currentModel.documentId || input.revision !== currentModel.revision) throw new Error('模型版本不匹配，请重新点选。');
  const part = currentModel.parts.find(p => p.id === input.selection?.objectId);
  if (!part) throw new Error('未找到选中零件。');
  if (typeof input.comment !== 'string' || !input.comment.trim() || input.comment.length > 2000) throw new Error('评论需为 1–2000 个字符。');
  const s = input.selection;
  if (!['surface', 'object'].includes(s.kind)) throw new Error('无效的选择类型。');
  if (s.kind === 'surface' && (!vector(s.worldPoint) || !vector(s.localPoint) || !vector(s.worldNormal) || !Number.isInteger(s.triangleIndex) || s.triangleIndex < 0 || !['+X','-X','+Y','-Y','+Z','-Z','cylindrical-wall'].includes(s.surface))) throw new Error('点选位置或表面信息无效。');
  if (s.kind === 'surface' && s.faceId !== undefined) {
    const face=preview?.meshes[part.id]?.faces?.find(face=>face.id===s.faceId);
    if (!face || s.triangleIndex < face.start || s.triangleIndex >= face.start+face.count) throw new Error('面引用与当前版本网格不匹配，请重新点选。');
  }
  if (!vector(input.camera?.position) || !vector(input.camera?.target)) throw new Error('视角信息无效。');
  const selection: Selection = s.kind === 'surface' ? {
    kind: s.kind, objectId: part.id, objectName: part.name, surface: s.surface,
    triangleIndex: s.triangleIndex, ...(s.faceId !== undefined ? {faceId:s.faceId} : {}), worldPoint: s.worldPoint, localPoint: s.localPoint, worldNormal: s.worldNormal,
  } : { kind: 'object', objectId: part.id, objectName: part.name };
  return { schema: 'cad-comment/v1', documentId: currentModel.documentId, revision: currentModel.revision, unit: currentModel.unit, upAxis: currentModel.upAxis, selection, objectParameters: structuredClone(part), camera: { position: input.camera.position, target: input.camera.target }, comment: input.comment.trim() };
}
