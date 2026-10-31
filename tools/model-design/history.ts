import type { Model, Revisions, UndoRequest, History, HistoryEntry } from './types.js';
import { validateDocument } from './model.js';

// Reconstruct the undo stack from committed revisions, including pre-history data.
export function operationHistory(revisions: Revisions): History {
  const entries: HistoryEntry[] = [], active: HistoryEntry[] = [];
  let previous: Model | undefined;
  for (const model of revisions.values()) {
    const op = model.lastOperation;
    if (previous && op) {
      const before = previous.parts.find(p => p.id === op.objectId);
      const after = model.parts.find(p => p.id === op.objectId);
      const entry: HistoryEntry = {
        id: model.revision, type: op.type, objectId: op.objectId,
        objectName: after?.name || before?.name, commentId: ('commentId' in op ? op.commentId : null) || null,
        requestId: ('request' in op ? op.request.requestId : null) || null,
        beforeParameters: before ? structuredClone(before) : null,
        afterParameters: after ? structuredClone(after) : null,
        previousRevision: previous.revision, revision: model.revision,
        createdAt: op.createdAt, undoOf: ('undoOf' in op ? op.undoOf : null),
        beforeDiameterMm: before?.kind==='cylinder' ? before.centerHoleDiameter || 0 : 0,
        afterDiameterMm: after?.kind==='cylinder' ? after.centerHoleDiameter || 0 : 0,
        beforeVolumeMm3: previous.geometry?.parts[op.objectId]?.volumeMm3,
        afterVolumeMm3: model.geometry?.parts[op.objectId]?.volumeMm3,
        status: 'applied',
      };
      if (op.type === 'undo') {
        if (active.at(-1)?.id !== op.undoOf) throw new Error('撤销记录与操作顺序不一致。');
        active.pop()!.status = 'undone';
      } else active.push(entry);
      entries.push(entry);
    }
    previous = model;
  }
  const external=previous?.parts.some(part=>(part.kind==='step' || part.kind==='native'));
  const externalUndo=previous?.lastOperation?.type==='sync-cad' && previous.lastOperation.mode==='edit';
  return { entries, undoOperationId: external && !externalUndo ? null : active.at(-1)?.id || null };
}

export function prepareUndo(input: UndoRequest, model: Model, revisions: Revisions): Model {
  validateDocument(input, model);
  if(model.parts.some(part=>(part.kind==='step' || part.kind==='native'))) throw new Error('请通过当前对话恢复 FreeCAD 原生文档，再同步快照；不能只撤销预览。');
  function fail(message: string): never { throw Object.assign(new Error(message), {status:409}); }
  if (input.expectedRevision !== model.revision) fail('模型版本已变化，请刷新后重新撤销。');
  const history = operationHistory(revisions);
  if (!history.undoOperationId || input.operationId !== history.undoOperationId) fail('只能撤销当前最近一条未撤销的编辑。');
  const target = history.entries.find(e => e.id === input.operationId);
  if (!target) throw new Error('找不到撤销目标。');
  const before = revisions.get(target.previousRevision);
  if (!before) fail('找不到修改前的模型，未执行撤销。');
  const next = structuredClone(model);
  next.name = before.name;
  next.parts = structuredClone(before.parts);
  next.revision = `r${Number(model.revision.slice(1)) + 1}`;
  next.lastOperation = {type:'undo', objectId:target.objectId, undoOf:target.id,
    restoredRevision:before.revision, previousRevision:model.revision, createdAt:new Date().toISOString()};
  delete next.geometry;
  return next;
}
