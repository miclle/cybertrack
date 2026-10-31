import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { BoxGeometry } from 'three';

// Synthetic UI fixtures only: no CAD, filesystem exports, or conversation writes.
function state(revision, height, undoOf = null) {
  const part = {
    id: 'external-01', name: 'UI 测试块', kind: 'step', color: '#a6bba0', position: [0, 0, 0],
    properties: { Length: 60, Width: 30, Height: height },
    source: { application: 'FreeCAD', documentName: 'UIFixture', documentUid: 'ui-fixture', objectName: 'Block', fingerprint: `fixture-${height}` },
  };
  const mesh = new BoxGeometry(60, 30, height).translate(30, 15, height / 2);
  const entry = {
    id: 'r3', type: 'sync-cad', objectId: part.id, objectName: part.name, commentId: null, requestId: null,
    beforeParameters: { ...part, properties: { ...part.properties, Height: 8 } },
    afterParameters: { ...part, properties: { ...part.properties, Height: 12 } },
    previousRevision: 'r2', revision: 'r3', createdAt: '2026-01-01T00:00:00Z', undoOf: null,
    beforeDiameterMm: 0, afterDiameterMm: 0, beforeVolumeMm3: 14400, afterVolumeMm3: 21600,
    status: undoOf === 'r3' ? 'undone' : 'applied',
  };
  return {
    model: { documentId: 'ui-fixture', revision, name: 'SolidCue 界面测试', unit: 'mm', upAxis: 'Z', parts: [part] },
    preview: { revision, engine: 'synthetic-ui-fixture', parts: {}, meshes: {
      [part.id]: { positions: Array.from(mesh.attributes.position.array), indices: Array.from(mesh.index.array),
        faces: mesh.groups.map((group, i) => ({ id: `Face${i + 1}`, type: 'Plane', start: group.start / 3, count: group.count / 3 })) },
    } },
    history: { undoOperationId: undoOf === 'r3' ? null : 'r3', entries: undoOf ? [entry, {
      ...entry, id: revision, type: 'undo', revision, previousRevision: 'r3', undoOf,
      beforeParameters: entry.afterParameters, afterParameters: part, status: 'applied',
    }] : [entry] },
    editing: false, revisions: [revision], stepExports: [], comments: [],
    transport: 'agent-pull', targetThreadId: null, nativeMessageBridge: true,
  };
}

export async function startUiHost() {
  const plugin = await readFile(new URL('./plugin/dist/model.html', import.meta.url));
  const fixtures = { initial: state('r3', 12), restored: state('r4', 8, 'r3'),
    unrelated: state('r4', 12, 'other-operation'), restoredAfterUnrelated: state('r5', 8, 'r3') };
  const host = `<!doctype html><meta charset="utf-8"><title>SolidCue UI fixture</title>
    <style>body{margin:12px;font:14px sans-serif;background:#fff}header{margin-bottom:12px}iframe{border:1px solid #bbb;display:block;width:390px;height:640px}button{margin:6px}</style>
    <header>合成数据 · 模拟 MCP 宿主 · 不连接 FreeCAD 或真实对话
      <label>卡片尺寸 <select id="size"><option>390×640</option><option>320×568</option><option>1280×720</option></select></label>
      <label><input id="reject" type="checkbox">拒绝撤销请求</label>
      <button id="restore" disabled>发布匹配的恢复快照</button><button id="unrelated" disabled>发布无关恢复记录</button>
      <output id="messages">0 条撤销请求</output>
    </header><iframe title="SolidCue 测试卡片" src="/model"></iframe>
    <script>
      const fixtures = ${JSON.stringify(fixtures)};
      let current = fixtures.initial, count = 0;
      const frame = document.querySelector('iframe');
      document.querySelector('#size').onchange = event => {
        const [width,height] = event.target.value.split('×');
        frame.style.width = width+'px';frame.style.height = height+'px';
      };
      for(const name of ['restore','unrelated']) document.querySelector('#'+name).onclick = () => {
        current = name === 'unrelated' ? fixtures.unrelated :
          current === fixtures.unrelated ? fixtures.restoredAfterUnrelated : fixtures.restored;
      };
      window.addEventListener('message', event => {
        if(event.source !== frame.contentWindow || event.origin !== location.origin) return;
        const request = event.data;
        if(request.jsonrpc !== '2.0' || request.id === undefined) return;
        const reply = result => event.source.postMessage({jsonrpc:'2.0',id:request.id,result}, location.origin);
        if(request.method === 'ui/initialize') return reply({
          protocolVersion: '2026-01-26', hostInfo: {name:'SolidCue UI test',version:'1.0.0'},
          hostCapabilities: {serverTools:{},experimental:{'openai/message':{}}}, hostContext: {theme:'light',displayMode:'inline'},
        });
        if(request.method === 'tools/call' && request.params.name === 'get_state')
          return reply({content:[],structuredContent:current});
        if(request.method === 'ui/message') {
          const text = request.params.content?.[0]?.text ?? '';
          if(!text.startsWith('请撤销 CyberTrack 模型设计')) return reply({isError:true});
          count++;document.querySelector('#messages').textContent = count+' 条撤销请求';
          if(document.querySelector('#reject').checked) return reply({isError:true});
          document.querySelector('#restore').disabled = false;
          document.querySelector('#unrelated').disabled = false;
          return reply({});
        }
        event.source.postMessage({jsonrpc:'2.0',id:request.id,error:{code:-32601,message:'Not supported by UI fixture'}}, location.origin);
      });
    </script>`;
  const server = createServer((request, response) => {
    if (!['/', '/model'].includes(request.url)) { response.writeHead(404).end(); return; }
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
    response.end(request.url === '/model' ? plugin : host);
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  return { url: `http://127.0.0.1:${server.address().port}`, close: () => new Promise(resolve => server.close(resolve)) };
}
