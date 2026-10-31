import {decodeState,geometryKey} from './state-codec.js';
import type { Api, ApiPath, State, StepRequest, SavedStep, StepArtifact, DownloadResult, CommentRecord } from './types.js';
import { toolData } from './mcp-result.js';
import { element as $ } from './dom.js';
import { errorMessage } from './errors.js';
import { App } from '@modelcontextprotocol/ext-apps';
import { OpenAIExtensions } from '@openai/mcp-extensions/app';

type McpApiPath = Extract<ApiPath, '/api/state' | '/api/comments' | '/api/geometry/undo'>;

const app = new App({ name: 'CyberTrack 模型设计', version: '0.9.2' });
const extensions = new OpenAIExtensions(app);
let resolveInitial: (state: State) => void;
const initialResult = new Promise<State>(resolve => { resolveInitial = resolve; });
app.ontoolresult = async result => {
  if (result.structuredContent?.model) { try { resolveInitial(await decodeState(result.structuredContent)); } catch { /* api supplies a fresh result */ } }
};
export async function getInitialState(): Promise<State> {
  return Promise.race([initialResult, api('/api/state')]);
}
try {
  await app.connect();
} catch (error) {
  $('status').textContent = `MCP 宿主连接失败：${errorMessage(error)}`;
  throw error;
}
export async function api<P extends McpApiPath>(path: P, ...args: Api[P]['input'] extends undefined ? [input?: undefined] : [input: Api[P]['input']]): Promise<Api[P]['output']> {
  const input=args[0];
  const tools: Record<McpApiPath,string> = { '/api/state': 'get_state', '/api/comments': 'save_comment', '/api/geometry/undo':'undo_model' };
  const name=tools[path];
  if (!name) throw new Error('不支持的 MCP 操作');
  const result = await app.callServerTool({ name, arguments: input ? (path === '/api/comments' ? { payload: input } : {...input}) : (path==='/api/state' && geometryKey() ? {geometryKey:geometryKey()} : {}) });
  const data=toolData<Api[P]['output']>(result,'MCP 调用失败');
  return (path==='/api/state' ? await decodeState(data) : data) as Api[P]['output'];
}
export function deliveryMode() { return extensions.message ? 'mcp-ui' : 'unsupported'; }
export function downloadHint() {
  if (app.getHostCapabilities()?.downloadFile) return '';
  return '将保存到本机导出目录。';
}
export async function downloadStep(input: StepRequest): Promise<DownloadResult> {
  const direct=!!app.getHostCapabilities()?.downloadFile;
  const result = await app.callServerTool({name:direct?'export_step':'save_step',arguments:{...input}},{timeout:15000});
  if(!direct) { const artifact=toolData<SavedStep>(result,'STEP 保存失败'); return {...artifact,message:`已保存并校验文件：${artifact.filePath}`}; }
  const artifact=toolData<StepArtifact>(result,'STEP 读取失败');
  const saved = await app.downloadFile({contents:[{type:'resource',resource:artifact.resource}]}, {timeout:60000});
  if (saved.isError) throw new Error('宿主未完成保存（可能已取消或拒绝）。');
  const {resource,...metadata}=artifact;
  return {...metadata, message:'宿主已接受保存请求，请在下载文件中核对。'};
}
export async function deliver(record: CommentRecord): Promise<void> {
  if (!extensions.message) throw new Error('宿主未声明 OpenAI 消息扩展，评论已保存但未发送。');
  if((record.payload.objectParameters.kind==='step' || record.payload.objectParameters.kind==='native')) {
    if(!extensions.message) throw new Error('当前宿主无法发送消息。');
    const result=await extensions.message.send({role:'user',content:[{type:'text',text:
      'CyberTrack 模型设计 外部 CAD 评论。先读取当前 get_state，校验 documentId/revision/commentId/hash；通过已连接 FreeCAD MCP 在原生文档修改。单实体使用 freecad_bridge.py 的 edit_properties；整机 native 零件使用 assembly_bridge.py 的 edit_placement，校验整个场景基线与原生 documentUid/fingerprint，只修改明确指定的位置坐标；不明确时澄清。将快照写入服务配置的 CAD_COMMENT_CAD_INBOX，再调用 sync_cad_snapshot(mode=edit)。失败不得伪报成功。执行前不得改用 CyberTrack 模型设计 本地建模工具。完成后 acknowledge_comment 记录实际结果。快照面 ID 仅在其原生 fingerprint 下有效。\n'+JSON.stringify(record)}],_meta:{'openai/message':{target:'active',send:true}}},{timeout:15000});
    if(result?.isError) throw new Error('宿主拒绝了消息。');
    return;
  }
  const text = `MCP-UI 模型评论：请直接确认目标和意图，并调用 acknowledge_comment 写回真实处理回执。此消息由内嵌模型界面通过 ui/message 发送到当前对话。隔离垫套支持 update_spacer_parameters：根据用户明确的尺寸意图，传入此评论 documentId、ID（commentId）、sha256、expectedRevision 及需要改变的绝对尺寸 outerDiameterMm / holeDiameterMm / heightMm（mm），省略的尺寸不变，底面保持 Z=0。相对高度变化应以快照 objectParameters.height 为基准换算。双孔安装板支持 update_plate_hole_spacing：传入此评论 documentId、commentId、sha256、expectedRevision 和绝对孔中心距 holeSpacingMm（mm），两孔对称移动至 X=±holeSpacingMm/2、Y=0，板尺寸、孔径和底面不变。若只说移动某个孔或意图含糊，先澄清，不能擅自换算为对称孔距。其他圆柱中心 Z 轴贯通孔可使用 apply_center_hole 和 diameterMm。成功后写回实际版本、尺寸与底面位置；没有变化应说明未创建版本。尺寸意图不明确应询问。仅收到评论不等于已修改。不要再次发送此消息。\n${JSON.stringify(record, null, 2)}`;
  const result = await extensions.message.send({ role: 'user', content: [{ type: 'text', text }], _meta: { 'openai/message': { target: 'active', send: true } } }, { timeout: 15000 });
  if (result?.isError) throw new Error('宿主拒绝了消息。');
}

export async function requestCadUndo(state: State): Promise<void> {
  if(!extensions.message) throw new Error('宿主未提供对话通道。');
  const result=await extensions.message.send({role:'user',content:[{type:'text',text:
    '请撤销 CyberTrack 模型设计 最近一次外部 CAD 修改：先读取 get_state 核对文档、版本与 history.undoOperationId，通过 FreeCAD MCP 恢复原生文档：单件使用 freecad_bridge.py undo_properties，整机使用 assembly_bridge.py undo_placement，校验 fingerprint；导出后调用 sync_cad_snapshot(mode=undo, operationId)。不能只切换预览。若原生文档已变化，停止撤销并同步实际状态。\n'+JSON.stringify({model:state.model,operationId:state.history.undoOperationId})}],_meta:{'openai/message':{target:'active',send:true}}},{timeout:15000});
  if(result?.isError) throw new Error('宿主拒绝了撤销请求。');
}
