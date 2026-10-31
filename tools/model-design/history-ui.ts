import type { State, PlatePart } from './types.js';
import { element as $ } from './dom.js';
import { errorMessage } from './errors.js';
import { api, requestCadUndo } from './transport.js';
let signature = '', current: State | undefined, pending = false;
let requestedCadUndo: string | null = null;
const diameter = (value: number) => value ? `Ø${value} mm` : '无孔';
const volume = (value: number | undefined) => typeof value==='number' && Number.isFinite(value) ? `${value.toFixed(3)} mm³` : '—';

export function syncHistory(state: State): void {
  current = state;
  const history = state.history || {entries:[],undoOperationId:null};
  if (requestedCadUndo && history.entries.some(entry => entry.undoOf === requestedCadUndo)) {
    $('history-status').textContent = `已恢复 FreeCAD 原生文档，当前版本 ${state.model.revision}。`;
    requestedCadUndo = null;
  }
  $('undo').disabled = pending || state.editing || !history.undoOperationId;
  const nextSignature = JSON.stringify(history);
  if (signature === nextSignature) return;
  signature = nextSignature;
  $('history-count').textContent = `${history.entries.length} 次操作`;
  $('history-empty').hidden = history.entries.length > 0;
  $('history-list').replaceChildren(...history.entries.slice().reverse().map(entry => {
    const card = document.createElement('article'); card.className = 'operation-card';
    card.setAttribute('aria-label', `操作 ${entry.id} ${entry.objectName}`);
    const head = document.createElement('div'); head.className='card-head';
    const title = document.createElement('h3'); title.textContent=`${entry.type === 'sync-cad' ? '同步 CAD 模型' : entry.type === 'undo' ? '撤销操作' : entry.type === 'create-spacer' ? '创建垫套' : entry.type === 'create-mounting-plate' ? '创建安装板' : entry.type === 'update-plate-hole-spacing' ? '修改对称孔距' : entry.type === 'update-spacer-parameters' ? '修改垫套尺寸' : '修改中心孔'} · ${entry.objectName}`;
    const badge = document.createElement('span'); badge.className='state received';
    badge.textContent=entry.type === 'undo' ? `已撤销 ${entry.undoOf}` : entry.status === 'undone' ? '已被撤销' : '已完成';
    head.append(title,badge);
    const table = document.createElement('table'); table.className='comparison';
    const caption = document.createElement('caption'); caption.textContent=`${entry.previousRevision} → ${entry.revision}`; table.append(caption);
    const before=entry.beforeParameters, after=entry.afterParameters;
    const plate=[before,after].some(part=>part?.profile==='mounting-plate');
    const formats: [string, (part: PlatePart) => string][] = [
      ['长 × 宽 × 厚',part=>`${part.size.join(' × ')} mm`],
      ['双贯通孔',part=>diameter(part.holeDiameter)],
      ['孔中心距',part=>`${part.holeSpacing} mm`],
      ['孔中心 XY',part=>`(±${part.holeSpacing/2}, 0) mm`],
      ['底面 Z',part=>`${part.position[2]-part.size[2]/2} mm`],
    ];
    const plateRows=plate ? formats.map(([label,format])=>[label,
      before?.profile==='mounting-plate' ? format(before) : '—',
      after?.profile==='mounting-plate' ? format(after) : '—']) : [
      ['中心贯通孔',before ? diameter(entry.beforeDiameterMm) : '—',after ? diameter(entry.afterDiameterMm) : '—'],
    ];
    const externalRows=((before?.kind==='step' || before?.kind==='native') || (after?.kind==='step' || after?.kind==='native')) ?
      [...new Set([...Object.keys((before?.kind==='step' || before?.kind==='native') ? before.properties : {}),...Object.keys((after?.kind==='step' || after?.kind==='native') ? after.properties : {})])].map(key=>
        [key,(before?.kind==='step' || before?.kind==='native') ? String(before.properties[key] ?? '—') : '—',(after?.kind==='step' || after?.kind==='native') ? String(after.properties[key] ?? '—') : '—']) : plateRows;
    const rows = [['对比项','修改前','修改后'],
      ['零件',before ? '存在' : '不存在',after ? '存在' : '不存在'],
      ...externalRows,
      ...([before,after].some(part=>part?.profile==='spacer') ? [
        ['外径',before?.kind==='cylinder' ? `Ø${before.radius*2} mm` : '—',after?.kind==='cylinder' ? `Ø${after.radius*2} mm` : '—'],
        ['高度',before?.kind==='cylinder' ? `${before.height} mm` : '—',after?.kind==='cylinder' ? `${after.height} mm` : '—'],
        ['底面 Z',before?.kind==='cylinder' ? `${before.position[2]-before.height/2} mm` : '—',after?.kind==='cylinder' ? `${after.position[2]-after.height/2} mm` : '—'],
      ] : []),
      ['零件体积',volume(entry.beforeVolumeMm3),volume(entry.afterVolumeMm3)]];
    rows.forEach((values,index) => {
      const row=document.createElement('tr');
      values.forEach((value,column) => {
        const cell=document.createElement(index===0 || column===0 ? 'th':'td');
        if(index===0)cell.scope='col';else if(column===0)cell.scope='row';
        cell.textContent=value;row.append(cell);
      }); table.append(row);
    });
    const details=document.createElement('details'), summary=document.createElement('summary');
    summary.textContent=entry.previousRevision+' → '+entry.revision+' · 查看变化';
    details.append(summary,table);card.append(head,details);
    if(entry.commentId) {
      const link=document.createElement('a');link.href=`#comment-${entry.commentId}`;link.textContent='查看来源评论';card.append(link);
    }
    return card;
  }));
}

export function setupUndo(refresh: () => Promise<void>): void {
  $('undo').addEventListener('click', async () => {
    if (pending || !current?.history?.undoOperationId) return;
    const input={documentId:current.model.documentId,expectedRevision:current.model.revision,operationId:current.history.undoOperationId};
    pending=true; $('undo').disabled=true; $('history-status').textContent='正在恢复修改前的实体并验证 STEP…';
    try {
      if(current.model.parts.some(part=>(part.kind==='step' || part.kind==='native'))) {
        await requestCadUndo(current);
        requestedCadUndo=input.operationId;
        $('history-status').textContent='已请求当前对话恢复 FreeCAD 文档，等待原生执行与快照同步。';
        return;
      }
      const result=await api('/api/geometry/undo',input);
      $('history-status').textContent=`已撤销 ${input.operationId}，当前版本 ${result.revision}。原有版本和记录均已保留。`;
    } catch(error) { $('history-status').textContent=`撤销未完成：${errorMessage(error)}`; }
    finally {pending=false;await refresh().catch(()=>{});if(current)syncHistory(current);}
  });
}
