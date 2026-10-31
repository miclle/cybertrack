import type { Model, Part, Preview, Selection, Vector3, Surface, CommentInput, CommentRecord, State } from './types.js';
import { element as $ } from './dom.js';
import { errorMessage } from './errors.js';
import { syncHistory, setupUndo } from './history-ui.js';
import { setupExport } from './export-ui.js';
import { setupWorkspace, openComment, closeComment } from './workspace-ui.js';
import { faceAt, faceHighlight } from './face-highlight.js';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { api, getInitialState, deliveryMode, deliver } from './transport.js';

setupWorkspace();
const initialState = await getInitialState().catch(error => {
  $('status').textContent = `模型读取失败：${errorMessage(error)}`;
  $('render-status').textContent = '模型读取失败';
  throw error;
});
let model = initialState.model;
let preview = initialState.preview;
let unavailable = false;
const drafts = new Map<string,string>();
const selectionKey = (value: Selection) => model.revision+':'+value.objectId+':'+(value.kind==='surface' ? value.faceId ?? value.triangleIndex : 'object');
function saveDraft() { if(selection) drafts.set(selectionKey(selection),$('comment').value); }
const syncExport = setupExport(model.documentId);

let selection: Selection | null = null;
let lastSignature = '';
let awaitingReceipt: string | null = null;
let submitting = false;
let pendingDelivery: {input: string;record: CommentRecord} | null = null;
let refreshing = false;
type PartMesh = THREE.Mesh<THREE.BufferGeometry, THREE.MeshStandardMaterial> & { userData: { part: Part } };
const meshes: PartMesh[] = [];
const scene = new THREE.Scene();
const hoveredFace=faceHighlight(scene,'#9dbd97',0.3);
const selectedFace=faceHighlight(scene,'#dfac70',0.45);
scene.background = new THREE.Color('#e9ece6');
const camera = new THREE.PerspectiveCamera(35, 1, 0.1, 2000);
camera.up.set(0, 0, 1);
const canvas = $('model-canvas');
let renderer: THREE.WebGLRenderer;
try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false }); }
catch (error) { $('webgl-error').hidden = false; $('webgl-error').textContent = `无法创建 WebGL 视图：${errorMessage(error)}`; $('render-status').textContent = 'WebGL 不可用'; throw error; }
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFShadowMap;
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.9;
const controls = new OrbitControls(camera, canvas);
controls.enableDamping = false;
controls.minDistance = 20;
controls.maxDistance = 650;
controls.maxPolarAngle = Math.PI * 0.86;
scene.add(new THREE.HemisphereLight(0xffffff, 0x819079, 2.6));
const light = new THREE.DirectionalLight(0xfff5dd, 3.1);
light.position.set(80, 40, 150);
light.castShadow = true;
Object.assign(light.shadow.camera, { left: -160, right: 160, top: 160, bottom: -160, near: 1, far: 500 });
light.shadow.mapSize.set(2048, 2048);
light.shadow.normalBias = 0.6;
scene.add(light);
const ground = new THREE.Mesh(new THREE.PlaneGeometry(1500, 1500), new THREE.MeshStandardMaterial({ color: '#e9ece6', roughness: 1 }));
ground.receiveShadow = true; ground.position.z = -0.4; scene.add(ground);
const grid = new THREE.GridHelper(320, 32, 0xb6c4b0, 0xd1d9c9);
grid.rotation.x = Math.PI / 2; grid.position.z = -0.1; grid.material.transparent = true; grid.material.opacity = 0.45; scene.add(grid);

function geometryFor(part: Part, preview: Preview): THREE.BufferGeometry {
  const data=preview?.meshes?.[part.id];
  if (!data) throw new Error('缺少实体内核预览网格。');
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(data.positions,3));
  geometry.setIndex(data.indices); geometry.computeVertexNormals(); geometry.computeBoundingSphere();
  return geometry;
}
function syncMeshes(nextModel: Model, preview: Preview): void {
  for (let i=meshes.length-1; i>=0; i--) {
    const mesh=meshes[i];
    if (!nextModel.parts.some(part=>part.id===mesh.userData.part.id)) {
      scene.remove(mesh); mesh.geometry.dispose(); mesh.material.dispose();
      for (const child of mesh.children as THREE.LineSegments<THREE.EdgesGeometry, THREE.LineBasicMaterial>[]) { child.geometry.dispose(); child.material.dispose(); }
      meshes.splice(i,1);
    }
  }
  $('parts').replaceChildren();
  for (const part of nextModel.parts) {
    const geometry=geometryFor(part,preview);
    let mesh=meshes.find(item=>item.userData.part.id===part.id);
    if (mesh) {
      mesh.geometry.dispose(); mesh.geometry=geometry; mesh.material.color.set(part.color);
      const edges=mesh.children[0] as THREE.LineSegments<THREE.EdgesGeometry, THREE.LineBasicMaterial>; edges.geometry.dispose(); edges.geometry=new THREE.EdgesGeometry(geometry,28);
    } else {
      mesh=new THREE.Mesh(geometry,new THREE.MeshStandardMaterial({color:part.color,roughness:0.43,metalness:part.id==='pin-01'?0.6:0.22})) as PartMesh;
      mesh.castShadow=true; mesh.receiveShadow=true;
      mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(geometry,28),new THREE.LineBasicMaterial({color:'#445c53',transparent:true,opacity:0.28})));
      scene.add(mesh); meshes.push(mesh);
    }
    mesh.position.set(...part.position); mesh.userData.part=part;
    const button=document.createElement('button');
    button.type='button'; button.dataset.id=part.id; button.setAttribute('aria-pressed','false');
    const swatch=document.createElement('i'); swatch.style.backgroundColor=part.color;
    button.append(swatch,document.createTextNode(part.name));
    button.addEventListener('click',()=>setSelection({kind:'object',objectId:part.id,objectName:part.name},[24,100]));
    $('parts').append(button);
  }
}
syncMeshes(model,initialState.preview);
const marker = new THREE.Mesh(new THREE.SphereGeometry(1.8, 16, 12), new THREE.MeshBasicMaterial({ color: '#f5b16e', depthTest: false }));
marker.renderOrder = 10; marker.visible = false; scene.add(marker);
const round = (value: number) => Math.round(value * 1000) / 1000;
const vec = (vector: THREE.Vector3): Vector3 => [round(vector.x),round(vector.y),round(vector.z)];
const fmt = (value: Vector3) => value.map(x => Number(x).toFixed(2)).join(', ');
const render = () => renderer.render(scene, camera);
controls.addEventListener('change', render);
controls.addEventListener('start',()=>{hoveredFace.clear();$('pick-label').hidden=true;closeComment();render();});
function reset() {
  if(model.parts.some(part=>(part.kind==='step' || part.kind==='native'))) {
    const box=new THREE.Box3();
    for(const mesh of meshes) box.expandByObject(mesh);
    const center=box.getCenter(new THREE.Vector3()), size=box.getSize(new THREE.Vector3());
    const distance=Math.max(size.x,size.y,size.z)*2.4;
    controls.minDistance=0.1;controls.maxDistance=Math.max(650,distance*5);
    camera.far=Math.max(2000,distance*10);camera.updateProjectionMatrix();
    controls.target.copy(center);camera.position.copy(center).add(new THREE.Vector3(distance,-distance,distance*0.75));
  } else if(model.parts.length===1 && model.parts[0].profile==='spacer') {
    const part=model.parts[0], distance=Math.max(part.radius*2,part.height)*3;
    camera.position.set(distance,distance,part.height/2+distance); controls.target.set(0,0,part.height/2);
  } else if(model.parts.length===1 && model.parts[0].profile==='mounting-plate') {
    const part=model.parts[0], distance=Math.max(...part.size)*1.6;
    camera.position.set(distance,distance,part.size[2]/2+distance); controls.target.set(0,0,part.size[2]/2);
  } else { camera.position.set(190,250,180); controls.target.set(0,0,27); }
  controls.update(); render();
}
function resize() { const rect = $('viewport').getBoundingClientRect(); camera.aspect = rect.width / rect.height; camera.updateProjectionMatrix(); renderer.setSize(rect.width, rect.height, false); render(); }
new ResizeObserver(resize).observe($('viewport'));
$('reset').addEventListener('click', reset);
reset(); resize();
$('render-status').textContent = '三维视图已就绪';

function setSelection(value: Selection, point: [number,number] = [24,100]): void {
  if(unavailable || submitting) return;
  saveDraft();
  selection = value;
  $('comment').value=drafts.get(selectionKey(value)) || '';
  $('draft-status').textContent=$('comment').value ? '已恢复草稿' : '';
  selectedFace.clear();hoveredFace.clear();
  if(value.kind==='surface') {
    const mesh=meshes.find(mesh=>mesh.userData.part.id===value.objectId);
    if(mesh) selectedFace.show(mesh,value.triangleIndex,faceAt(preview.meshes[value.objectId]?.faces,value.triangleIndex));
  }
  for (const mesh of meshes) {
    const active = value.kind==='object' && mesh.userData.part.id === value.objectId;
    mesh.material.emissive.set(active ? '#435e37' : '#000000'); mesh.material.emissiveIntensity = active ? 0.28 : 0;
  }
  for (const button of $('parts').querySelectorAll('button')) button.setAttribute('aria-pressed', String(button.dataset.id === value.objectId));
  marker.visible = value.kind === 'surface';
  if (value.kind==='surface') marker.position.set(...value.worldPoint).addScaledVector(new THREE.Vector3(...value.worldNormal), 0.7);
  $('selection-info').hidden = false; $('selection-hint').hidden = true;
  $('part-name').textContent = value.objectName;
  $('pick-type').textContent = value.kind === 'surface' ? value.faceId ? value.faceId+' · 当前版本' : '表面点 · 旧网格无面映射' : '整个零件';
  const entries = [['零件 ID', value.objectId], ['模型版本', model.revision]];
  const selectedPart=model.parts.find(p=>p.id===value.objectId);
  $('comment').placeholder=selectedPart?.profile==='mounting-plate'
    ? '例如：两孔中心距改为 44 mm，关于板中心对称，其他尺寸不变。'
    : '例如：把这个垫套加高 4 mm，底面不动，两个直径保持不变。';
  if((selectedPart?.kind==='step' || selectedPart?.kind==='native')) {
    $('comment').placeholder=selectedPart.kind==='native' ? '例如：将这个零件沿 Z 轴上移 5 mm，其他零件保持不变。' : '例如：把 Height 改为 12 mm，其他属性保持不变。';
    if(selectedPart.kind==='native') entries.push(['可调整范围','静态零件位置；形状修改需原生 CAD 建模']);
    entries.push(['来源', 'FreeCAD · '+selectedPart.source.objectName]);
    for(const [name,value] of Object.entries(selectedPart.properties)) entries.push([name,value+' mm']);
  }
  if(selectedPart?.profile==='spacer') entries.push(['外径', `Ø${selectedPart.radius*2} mm`], ['高度', `${selectedPart.height} mm`], ['底面基准', 'Z=0 mm']);
  if(selectedPart?.profile==='mounting-plate') entries.push(
    ['长 × 宽 × 厚', `${selectedPart.size.join(' × ')} mm`],
    ['双贯通孔', `Ø${selectedPart.holeDiameter} mm · Z 轴`],
    ['孔中心距', `${selectedPart.holeSpacing} mm`],
    ['孔中心 XY', `(${ -selectedPart.holeSpacing/2}, 0)、(${selectedPart.holeSpacing/2}, 0) mm`],
    ['底面基准', 'Z=0 mm']);
  if(selectedPart?.kind==='cylinder' && selectedPart.centerHoleDiameter) entries.push(['中心贯通孔', `Ø${selectedPart.centerHoleDiameter} mm · Z 轴`]);
  if (value.kind === 'surface' && value.faceId) entries.push(['CAD 面', value.faceId+'（仅此版本）']);
  if (value.kind === 'surface') entries.push(['表面', value.surface], ['世界坐标 / mm', fmt(value.worldPoint)], ['局部坐标 / mm', fmt(value.localPoint)], ['世界法向', fmt(value.worldNormal)]);
  $('selection-fields').replaceChildren(...entries.map(([label, content]) => {
    const row = document.createElement('div'); const dt = document.createElement('dt'); const dd = document.createElement('dd'); dt.textContent = label; dd.textContent = content; row.append(dt, dd); return row;
  }));
  $('pick-label').hidden = true; $('pick-label').textContent = `${value.objectName} · ${value.kind === 'surface' ? value.surface + ' · ' + fmt(value.worldPoint) + ' mm' : '整个零件'}`;
  $('status').textContent = ''; updateSubmit(); openComment(point); render();
}
const raycaster = new THREE.Raycaster();
let pointerStart: [number,number] | null = null;
let dragged = false;
canvas.addEventListener('pointerdown', event => { if (event.button === 0) { pointerStart = [event.clientX, event.clientY]; dragged = false; } });
function hitAt(event: PointerEvent) {
  const rect=canvas.getBoundingClientRect();
  raycaster.setFromCamera(new THREE.Vector2((event.clientX-rect.left)/rect.width*2-1,-(event.clientY-rect.top)/rect.height*2+1),camera);
  return raycaster.intersectObjects(meshes,false)[0];
}
canvas.addEventListener('pointermove', event => {
  if(pointerStart && Math.hypot(event.clientX-pointerStart[0],event.clientY-pointerStart[1])>5) dragged=true;
  if(pointerStart || event.buttons || unavailable) {hoveredFace.clear();$('pick-label').hidden=true;render();return;}
  const hit=hitAt(event);
  if(!hit?.face || hit.faceIndex==null) {hoveredFace.clear();$('pick-label').hidden=true;canvas.style.cursor='';render();return;}
  const part=hit.object.userData.part as Part;
  const face=faceAt(preview.meshes[part.id]?.faces,hit.faceIndex);
  hoveredFace.show(hit.object as THREE.Mesh,hit.faceIndex,face);canvas.style.cursor='pointer';
  const rect=canvas.getBoundingClientRect(), label=$('pick-label');
  label.textContent=part.name+' · '+(face ? face.id : '表面点');
  label.hidden=false;
  label.style.left=Math.max(12,Math.min(event.clientX-rect.left+14,rect.width-label.offsetWidth-12))+'px';
  label.style.top=Math.max(78,Math.min(event.clientY-rect.top+18,rect.height-label.offsetHeight-12))+'px';
  render();
});
canvas.addEventListener('pointerleave',()=>{hoveredFace.clear();$('pick-label').hidden=true;canvas.style.cursor='';render();});
canvas.addEventListener('pointercancel', () => { pointerStart = null; });
canvas.addEventListener('pointerup', event => {
  const start = pointerStart; pointerStart = null;
  if (event.button !== 0 || !start || dragged || unavailable || submitting) return;
  const rect = canvas.getBoundingClientRect();
  raycaster.setFromCamera(new THREE.Vector2((event.clientX - rect.left) / rect.width * 2 - 1, -(event.clientY - rect.top) / rect.height * 2 + 1), camera);
  const hit = raycaster.intersectObjects(meshes, false)[0];
  if (!hit?.face || hit.faceIndex==null) {closeComment();return;}
  const local = hit.object.worldToLocal(hit.point.clone());
  const localNormal = hit.face.normal.clone();
  const normal = localNormal.clone().applyNormalMatrix(new THREE.Matrix3().getNormalMatrix(hit.object.matrixWorld)).normalize();
  const axes = ['X', 'Y', 'Z']; const values = localNormal.toArray();
  const axis = values.map(Math.abs).indexOf(Math.max(...values.map(Math.abs)));
  const part = hit.object.userData.part;
  const surface: Surface = part.kind === 'cylinder' && Math.abs(localNormal.z) < 0.9 ? 'cylindrical-wall' : `${values[axis] >= 0 ? '+' : '-'}${axes[axis]}` as Surface;
  const face=faceAt(preview.meshes[part.id]?.faces,hit.faceIndex);
  setSelection({ ...(face ? {faceId:face.id} : {}), kind: 'surface', objectId: part.id, objectName: part.name, surface, triangleIndex: hit.faceIndex, worldPoint: vec(hit.point), localPoint: vec(local), worldNormal: vec(normal) },[event.clientX-rect.left,event.clientY-rect.top]);
});
function updateSubmit() { $('submit').disabled = submitting || unavailable || !selection || !$('comment').value.trim(); }
$('comment').addEventListener('input',()=>{saveDraft();updateSubmit();});
function payload(): CommentInput { if (!selection) throw new Error('请先选择零件。'); return { documentId: model.documentId, revision: model.revision, selection: structuredClone(selection), camera: { position: vec(camera.position), target: vec(controls.target) }, comment: $('comment').value.trim() }; }
$('submit').addEventListener('click', async () => {
  if ($('submit').disabled || submitting) return;
  submitting = true;
  const snapshot = payload(); $('submit').disabled = true; $('status').textContent = '正在保存…';
  try {
    const serialized=JSON.stringify(snapshot);
    const record=pendingDelivery?.input===serialized ? pendingDelivery.record : await api('/api/comments', snapshot);
    pendingDelivery={input:serialized,record};
    awaitingReceipt = record.id;

    $('status').textContent = '已保存。';
    if (['mcp-ui','codex-cli-queue'].includes(deliveryMode())) { await deliver(record); $('status').textContent = '宿主已接受消息，等待当前 AI 处理回执。'; }
    else $('status').textContent = '本地已保存，当前页面没有宿主消息桥。';
    if ($('comment').value.trim() === snapshot.comment) { $('comment').value = ''; saveDraft(); }
    pendingDelivery=null;closeComment();
    await refresh();
  } catch (error) { $('status').textContent = `提交未完成：${errorMessage(error)} 草稿已保留，可在历史中核对已保存的评论。`; }
  finally { submitting = false; updateSubmit(); await refresh().catch(() => {}); }
});
function packetText(record: CommentRecord): string {
  const p = record.payload; const s = p.selection;
  return [`CAD_COMMENT_ID=${record.id}`, `document=${p.documentId}; revision=${p.revision}; unit=${p.unit}; up=${p.upAxis}`, `object=${s.objectId}; name=${s.objectName}; kind=${s.kind}`,
    ...(s.kind === 'surface' ? [`surface=${s.surface}; face=${s.faceId || "unmapped"}; triangle=${s.triangleIndex} (仅此版本网格索引)`, `world_point=[${s.worldPoint}]; local_point=[${s.localPoint}]; world_normal=[${s.worldNormal}]`] : []),
    `camera=[${p.camera.position}]; target=[${p.camera.target}]`, `comment=${p.comment}`].join('\n');
}
function renderComments(records: CommentRecord[]): void {
  $('comment-count').textContent = `${records.length} 条`;
  $('empty-comments').hidden = records.length > 0;
  $('comments').replaceChildren(...records.slice().reverse().map(record => {
    const card = document.createElement('article'); card.className = 'comment-card'; card.id = `comment-${record.id}`;
    card.setAttribute('aria-label', `CAD 评论目标 ${record.payload.selection.objectName} ${record.id}`);
    const head = document.createElement('div'); head.className = 'card-head';
    const title = document.createElement('h3'); title.textContent = record.payload.selection.objectName + ' / ' + record.payload.revision;
    const state = document.createElement('span'); state.className = 'state' + (record.receipt || record.processing?.status === 'completed' ? ' received' : ''); state.textContent = (({processing:'正在修改',completed:record.processing?.changed===false ? '无需修改' : '几何修改已完成',failed:'修改失败'} as Record<string,string>))[record.processing?.status || ''] || (record.receipt ? '当前 AI 已读取' : record.delivery?.status === 'queued' ? '已进入对话队列 · 待处理' : '已保存 · 等待处理'); head.append(title, state);
    const comment = document.createElement('p'); comment.className = 'comment-text'; comment.textContent = record.payload.comment;
    const data = document.createElement('pre'); data.className = 'target-data'; data.textContent = packetText(record);
    const copy = document.createElement('button'); copy.className = 'copy'; copy.textContent = '复制目标与评论 ↗';
    copy.addEventListener('click', async () => { try { await navigator.clipboard.writeText(packetText(record)); copy.textContent = '已复制，可粘贴到当前聊天'; } catch { copy.textContent = '复制不可用，请选中卡片文字复制'; } });
    const hint = document.createElement('div'); hint.className = 'native-hint'; hint.textContent = record.delivery ? `投递状态：${record.delivery.status} · ${record.delivery.transport || '结果待确认'}` : '目标快照保存在本机。';
    if (!record.receipt && !record.delivery && ['mcp-ui','codex-cli-queue'].includes(deliveryMode())) {
      const retry = document.createElement('button'); retry.className = 'copy'; retry.textContent = '发送此评论到当前对话';
      retry.addEventListener('click', async () => { retry.disabled = true; try { await deliver(record); retry.textContent = '已提交，等待 AI 回执'; } catch (error) { retry.textContent = errorMessage(error); } });
      card.append(retry);
    }
    const details=document.createElement('details'), summary=document.createElement('summary');
    summary.textContent='目标快照';details.append(summary,data,copy,hint);
    card.append(head, comment, details);
    if(record.processing?.message) { const progress=document.createElement('p'); progress.className=record.processing.status === 'failed' ? 'processing-error' : 'processing-note'; progress.textContent=record.processing.message;card.append(progress); }
    if (record.receipt) { const receipt = document.createElement('div'); receipt.className = 'receipt'; receipt.textContent = 'AI 回执：' + record.receipt.message; card.append(receipt); }
    return card;
  }));
}
function clearSelection() {
  saveDraft();selection=null; marker.visible=false;
  selectedFace.clear();hoveredFace.clear();
  for(const mesh of meshes) mesh.material.emissive.set('#000000');
  $('selection-info').hidden=true; $('selection-hint').hidden=false; $('pick-label').hidden=true;
  $('pick-type').textContent='等待点选'; closeComment();updateSubmit();
}
function syncModel(state: State): void {
  if(state.model.documentId !== model.documentId) {
    unavailable=true;clearSelection(); $('undo').disabled=true; $('comment').disabled=true;
    throw new Error('服务已切换文档，请打开当前文档的新卡片。');
  }
  syncExport(state);
  if(state.model.revision !== model.revision) {
    const wasEmpty=model.parts.length===0;
    clearSelection();
    syncMeshes(state.model,state.preview);
    model=state.model;preview=state.preview;marker.visible=false;
    $('draft-status').textContent=$('comment').value ? '旧版本草稿 · 请复制后重新选面' : '';
    if(wasEmpty && model.parts.length) reset();
    $('status').textContent=model.parts.length ? `实体已更新到 ${model.revision}；旧表面点已清除，请重新点选。` : `已恢复空白文档 · ${model.revision}。可以在当前对话中创建垫套或双孔安装板。`;
    render();
  }
  $('model-title').textContent=model.name;
  $('model-canvas').setAttribute('aria-label',`可旋转、缩放、点击选择的三维模型：${model.name}`);
  $('model-info').textContent=`${model.parts.length} 个零件 · ${model.revision} · mm · OpenCascade 实体`;
  $('empty-model').hidden=model.parts.length>0;
  $('selection-hint').textContent=model.parts.length ? '在模型上点一下。位置来自三维拾取，无需截图猜测。' : '还没有零件。先在当前对话中指定零件类型和尺寸，创建垫套或双孔安装板。';
  const target=model.parts.find(p=>p.id===model.lastOperation?.objectId);
  $('geometry-result').textContent=!model.parts.length ? `${model.revision} · 空白文档 · 无 STEP 产物` : target ? `${model.revision} · ${target.name} · ${target.kind==='cylinder' && target.centerHoleDiameter ? `中心贯通孔 Ø${target.centerHoleDiameter} mm` : '无中心孔'}${target.profile==='spacer' ? ` · 外径 Ø${target.radius*2} mm · 高度 ${target.height} mm · 底面 Z=0` : ''} · STEP 已验证` : `${model.revision} · 原始实体 · STEP 已验证`;
  if(target?.profile==='mounting-plate') $('geometry-result').textContent=
    `${model.revision} · ${target.name} · ${target.size.join(' × ')} mm · 双孔 Ø${target.holeDiameter} mm · 孔距 ${target.holeSpacing} mm · 底面 Z=0 · STEP 已验证`;
  if((target?.kind==='step' || target?.kind==='native')) $('geometry-result').textContent=model.revision+' · FreeCAD 原生文档快照 · 当前版本面映射；原生整机预览不等于 STEP 验证';
  syncHistory(state);
  unavailable=state.editing;
  $('render-status').textContent=state.editing ? '正在更新模型…' : model.revision+(model.parts.some(part=>(part.kind==='step' || part.kind==='native')) ? ' · FreeCAD 快照' : '')+' · '+(deliveryMode()==='mcp-ui' ? '已连接当前对话' : '本地预览');
  updateSubmit();
}
async function refresh() {
  if(refreshing) return;
  refreshing=true;
  try {
  const state = await api('/api/state'); syncModel(state); const signature = JSON.stringify(state.comments);
  if (awaitingReceipt && state.comments.some(record => record.id === awaitingReceipt && record.receipt)) {
    $('status').textContent = '当前对话已读取这条评论。可在历史中查看回执。';
    awaitingReceipt = null;
  }
  if (signature !== lastSignature) { lastSignature = signature; renderComments(state.comments); }
  } finally {refreshing=false;}
}
if (deliveryMode() === 'mcp-ui') { $('submit').textContent = '发送到当前对话 ↗'; document.querySelector<HTMLDetailsElement>('.bridge')!.innerHTML = '<summary>MCP 对话连接</summary><p>提交会保存目标快照，并通过宿主 ui/message 发送到当前对话。收到真实处理回执后才显示 AI 已读取。</p>'; }
setupUndo(refresh);
syncModel(initialState);
await refresh();
if (deliveryMode() === 'codex-cli-queue') { $('submit').textContent = '发送到当前对话 ↗'; document.querySelector<HTMLDetailsElement>('.bridge')!.innerHTML = '<summary>已连接当前对话</summary><p>网页通过本机服务调用官方 codex queue，发送到启动时绑定的当前对话。AI 正在处理时会排队。MCP 插件已安装；内嵌 ui/message 通道仍待宿主验证。</p>'; }
setInterval(() => { if (!document.hidden) refresh().catch(error => {
  unavailable=true;updateSubmit();$('undo').disabled=true;
  $('render-status').textContent='连接中断 · 预览可能已过期';$('status').textContent=errorMessage(error);
}); }, 2000);
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh().catch(() => {}); });
