import {decodeState,geometryKey} from './state-codec.js';
import type { App } from '@modelcontextprotocol/ext-apps';
import type { OpenAIExtensions } from '@openai/mcp-extensions/app';
import type { Api, ApiPath, State, StepRequest, SavedStep, StepArtifact, DownloadResult, CommentRecord } from './types.js';
import { toolData } from './mcp-result.js';
const embedded = (globalThis as typeof globalThis & {__MCP_APP__?: boolean}).__MCP_APP__ === true;
let app: App | undefined, extensions: OpenAIExtensions | undefined;
let localMode = 'local';
if (embedded) {
  const [{ App }, { OpenAIExtensions }] = await Promise.all([
    import('@modelcontextprotocol/ext-apps'), import('@openai/mcp-extensions/app'),
  ]);
  app = new App({ name: 'CyberTrack 模型设计', version: '0.1.0' });
  extensions = new OpenAIExtensions(app);
  await app.connect();
}
export async function api<P extends ApiPath>(path: P, ...args: Api[P]['input'] extends undefined ? [input?: undefined] : [input: Api[P]['input']]): Promise<Api[P]['output']> {
  const input=args[0];
  if (app) {
    const tools: Partial<Record<ApiPath,string>> = { '/api/state': 'get_state', '/api/comments': 'save_comment' };
    const name=tools[path];
    if (!name) throw new Error('不支持的 MCP 操作');
    const result = await app.callServerTool({ name, arguments: input ? { payload: input } : (path==='/api/state' && geometryKey() ? {geometryKey:geometryKey()} : {}) });
    const data=toolData<Api[P]['output']>(result,'MCP 调用失败');
  return (path==='/api/state' ? await decodeState(data) : data) as Api[P]['output'];
  }
  const endpoint=path==='/api/state' ? path+'?preview=gzip'+(geometryKey()?'&geometryKey='+encodeURIComponent(geometryKey()!):'') : path;
  const response = await fetch(endpoint, input ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input) } : {});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '评论服务不可用');
  if (path === '/api/state' && result.transport === 'codex-cli-queue') localMode = 'codex-cli-queue';
  return (path==='/api/state' ? await decodeState(result) : result) as Api[P]['output'];
}
export function deliveryMode() { return app ? (extensions?.message ? 'mcp-ui' : 'unsupported') : localMode; }
export function messageText(record: CommentRecord): string {
  return `来自 CyberTrack 模型设计 的模型评论。请确认目标和意图，并用 acknowledge_comment 写回真实处理回执。仅描述实际执行结果，未经几何工具确认勿声称已修改几何。\n${JSON.stringify(record, null, 2)}`;
}
export async function deliver(record: CommentRecord) {
  if (!app && localMode === 'codex-cli-queue') return api('/api/send', { id: record.id, sha256: record.sha256 });
  if (!extensions?.message) throw new Error('当前宿主未提供 MCP ui/message 消息能力；评论已保留。');
  const result = await extensions.message.send({ role: 'user', content: [{ type: 'text', text: messageText(record) }], _meta: { 'openai/message': { target: 'active', send: true } } });
  if (result?.isError) throw new Error('宿主拒绝了消息。');
  return undefined;
}

export async function getInitialState(): Promise<State> { return api('/api/state'); }
export function downloadHint() { return app && !app.getHostCapabilities()?.downloadFile ? '将保存到本机导出目录。' : ''; }
export async function downloadStep(input: StepRequest): Promise<DownloadResult> {
  let artifact: StepArtifact;
  if (app) {
    const direct=!!app.getHostCapabilities()?.downloadFile;
    const result = await app.callServerTool({name:direct?'export_step':'save_step',arguments:{...input}},{timeout:15000});
    if(!direct) { const saved=toolData<SavedStep>(result,'STEP 保存失败'); return {...saved,message:`已保存并校验文件：${saved.filePath}`}; }
    artifact=toolData<StepArtifact>(result,'STEP 读取失败');
    const saved = await app.downloadFile({contents:[{type:'resource',resource:artifact.resource}]}, {timeout:60000});
    if (saved.isError) throw new Error('宿主未完成保存（可能已取消或拒绝）。');
  } else {
    artifact = await api('/api/export-step', input);
    const bytes = Uint8Array.from(atob(artifact.resource.blob), char=>char.charCodeAt(0));
    const url = URL.createObjectURL(new Blob([bytes], {type:artifact.resource.mimeType}));
    const link = document.createElement('a');
    link.href=url; link.download=artifact.filename; document.body.append(link); link.click(); link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),60000);
  }
  const {resource,...metadata}=artifact;
  return {...metadata, message:'已请求保存，请在下载文件中核对。'};
}

export async function requestCadUndo(_state: State): Promise<void> {
  throw new Error('请在当前对话请求恢复 FreeCAD 原生文档，独立预览不能直接撤销外部 CAD。');
}
