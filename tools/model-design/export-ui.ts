import type { State } from './types.js';
import { element as $ } from './dom.js';
import { errorMessage } from './errors.js';
import { downloadHint, downloadStep } from './transport.js';

export function setupExport(documentId: string): (state: State) => void {
  const revision = $('export-revision');
  const part = $('export-part');
  const button = $('export-step');
  const status = $('export-status');
  const hint = $('export-hint');
  let state: State | undefined, busy = false, signature = '';
  function render() {
    const current=state;
    if (!current) return;
    const matching = current.model.documentId === documentId;
    const catalog = matching ? current.stepExports || [] : [];
    const nextSignature = JSON.stringify([current.model.revision,catalog]);
    if (signature !== nextSignature) {
      const previous = revision.value || 'current';
      revision.replaceChildren(new Option(`当前版本 · ${current.model.revision}`, 'current'),
        ...catalog.filter(item=>item.revision!==current.model.revision).reverse().map(item=>
          new Option(`${item.revision}${item.parts.length ? '' : ' · 无 STEP'}`,item.revision)));
      revision.value = [...revision.options].some(option=>option.value===previous) ? previous : 'current';
      signature = nextSignature;
    }
    const chosen = catalog.find(item=>item.revision===(revision.value==='current' ? current.model.revision : revision.value));
    const choices = chosen?.parts || [];
    const previousPart = part.value;
    const targets = [...choices, ...(choices.length>1 ? [{id:'assembly',name:'完整模型'}] : [])];
    if (JSON.stringify([...part.options].map(option=>[option.value,option.textContent])) !== JSON.stringify(targets.map(item=>[item.id,item.name]))) {
      part.replaceChildren(...targets.map(item=>new Option(item.name,item.id)));
      if ([...part.options].some(option=>option.value===previousPart)) part.value=previousPart;
    }
    revision.disabled = busy || !matching;
    part.disabled = busy || !choices.length || !matching;
    button.disabled = busy || !matching || current.editing || !choices.length;
    hint.textContent = !matching ? '文档已切换，请打开当前文档的新卡片。'
      : !choices.length ? '此版本没有 STEP 产物；整机预览请从 FreeCAD 导出。'
      : current.editing ? '正在更新模型，完成后可下载。'
      : `${chosen?.revision} · ${part.selectedOptions[0]?.textContent} · mm · 已验证的 STEP ${downloadHint()}`;
  }
  revision.addEventListener('change',()=>{status.textContent='';render();});
  part.addEventListener('change',()=>{status.textContent='';render();});
  button.addEventListener('click',async()=>{
    if (button.disabled || !state) return;
    const input = {documentId,revision:revision.value==='current' ? state.model.revision : revision.value,partId:part.value};
    busy=true; render(); status.textContent=`正在准备 ${input.revision} 的 STEP…`;
    try {
      const artifact=await downloadStep(input);
      status.textContent=`${artifact.message} ${artifact.filename} · ${artifact.byteLength} 字节 · SHA-256 ${artifact.sha256}`;
    } catch(error) {status.textContent=`下载未完成：${errorMessage(error)}`;}
    finally {busy=false;render();}
  });
  return nextState=>{state=nextState;render();};
}
