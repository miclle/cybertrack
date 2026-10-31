import type { CallToolResult } from '@modelcontextprotocol/sdk/types.js';
import { errorMessage, inputObject } from './errors.js';
import { readFile } from 'node:fs/promises';
import { McpServer } from '@modelcontextprotocol/sdk/server/mcp.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import { registerAppTool, registerAppResource, RESOURCE_MIME_TYPE } from '@modelcontextprotocol/ext-apps/server';
import { z } from 'zod';
const server = new McpServer({ name: 'cad-comment-lab', version: '0.9.2' });
const uri = 'ui://cad-comment/model.html';
async function request(path: string, input?: object): Promise<CallToolResult> {
  try {
    const response = await fetch(`http://127.0.0.1:9473${path}`, input ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(input), signal: AbortSignal.timeout((path.startsWith('/api/geometry/') || path.startsWith('/api/cad/')) ? 65000 : 5000) } : { signal: AbortSignal.timeout(5000) });
    const data = inputObject(await response.json());
    if (!response.ok) throw new Error(typeof data.error==='string' ? data.error : '服务请求失败。');
    const {preview,previewCompressed,resource,...summary}=data;
    return { content: [{ type: 'text', text: JSON.stringify(summary) }], structuredContent: data };
  } catch (error) { return { isError: true, content: [{ type: 'text', text: errorMessage(error) }] }; }
}
server.registerTool('undo_model', {
  description:'Undo the latest active modeling operation after user authorization, including creation back to an empty document. Requires the current documentId, revision and operation ID returned by get_state.history.undoOperationId. Creates a new immutable revision and updates the existing preview; never erases history.',
  inputSchema:{documentId:z.string().min(1),expectedRevision:z.string().regex(/^r[1-9][0-9]*$/),operationId:z.string().regex(/^r[1-9][0-9]*$/)},
  annotations:{destructiveHint:false,openWorldHint:false},
}, input=>request('/api/geometry/undo',input));
server.registerTool('create_spacer', {
  description:'Create one cylindrical spacer in the current empty document. Dimensions are mm: outer diameter, through-hole diameter, height. Bottom center stays at (0,0,0), axis +Z. Requires explicit user intent, current document/revision and a unique requestId. Validates the solid and STEP before committing; Undo restores the empty document. Replaying the identical request returns the original operation and its current status, never recreates an undone part.',
  inputSchema:{documentId:z.string().min(1),expectedRevision:z.string().regex(/^r[1-9][0-9]*$/),
    requestId:z.string().regex(/^[a-zA-Z0-9_-]{1,128}$/),
    outerDiameterMm:z.number().positive(),holeDiameterMm:z.number().positive(),heightMm:z.number().positive()},
  annotations:{destructiveHint:false,openWorldHint:false},
}, input=>request('/api/geometry/spacer',input));
const readOnly = { readOnlyHint: true, destructiveHint: false, openWorldHint: false };
server.registerTool('create_mounting_plate', {
  description:'Create one rectangular mounting plate with two Z-axis through-holes in the current empty document. Dimensions are mm. Bottom center is (0,0,0); holes are at X = ±holeSpacingMm/2, Y = 0. Requires explicit user intent, current document/revision and unique requestId. Validates exact solid, hole geometry and STEP before committing. Undo restores the empty document; replaying an identical request never recreates an undone part. Use update_plate_hole_spacing for comment-based spacing edits.',
  inputSchema:z.strictObject({documentId:z.string().min(1),expectedRevision:z.string().regex(/^r[1-9][0-9]*$/),
    requestId:z.string().regex(/^[a-zA-Z0-9_-]{1,128}$/),
    lengthMm:z.number().positive(),widthMm:z.number().positive(),thicknessMm:z.number().positive(),
    holeDiameterMm:z.number().positive(),holeSpacingMm:z.number().positive()}),
  annotations:{destructiveHint:false,openWorldHint:false},
}, input=>request('/api/geometry/mounting-plate',input));
server.registerTool('export_step', {
  description: 'Read an already verified STEP artifact from a specified document, immutable revision and part (or assembly). Returns filename, SHA-256 and an embedded resource for the host download-file channel. Does not modify geometry or save a file on the user device by itself.',
  inputSchema: z.strictObject({documentId:z.string().min(1),revision:z.string().regex(/^r[1-9][0-9]*$/),partId:z.string().regex(/^[a-zA-Z0-9_-]+$/)}),
  annotations: readOnly,
}, input=>request('/api/export-step',input));
server.registerTool('save_step', {
  description: 'Save an already verified STEP from a specified document/revision/part into the configured local export directory (default Downloads/SolidCue). Use after an explicit export/download request or card button click. Verifies the saved SHA-256, reuses identical files, refuses to overwrite different contents, returns the actual absolute filePath. Never edits the model. The destination is server-configured, not an input path.',
  inputSchema:z.strictObject({documentId:z.string().min(1),revision:z.string().regex(/^r[1-9][0-9]*$/),partId:z.string().regex(/^[a-zA-Z0-9_-]+$/)}),
  annotations:{readOnlyHint:false,destructiveHint:false,idempotentHint:true,openWorldHint:false},
}, input=>request('/api/save-step',input));
server.registerTool('update_spacer_parameters', {
  description:'Update the spacer selected by an immutable saved comment. Requires explicit user intent and current documentId, revision, comment ID and hash. Supply at least one absolute dimension in mm; omitted dimensions stay unchanged. Bottom center stays at (0,0,0), axis +Z. Validates solid and STEP before publishing an immutable revision; identical dimensions return changed:false without a new revision. Undo restores the previous dimensions.',
  inputSchema:z.strictObject({documentId:z.string().min(1),expectedRevision:z.string().regex(/^r[1-9][0-9]*$/),
    commentId:z.string().uuid(),sha256:z.string().regex(/^[a-f0-9]{64}$/),
    outerDiameterMm:z.number().positive().optional(),holeDiameterMm:z.number().positive().optional(),heightMm:z.number().positive().optional()}),
  annotations:{destructiveHint:false,openWorldHint:false},
}, input=>request('/api/geometry/spacer-parameters',input));
server.registerTool('update_plate_hole_spacing', {
  description:'Update only the symmetric center-to-center hole spacing of the mounting plate selected by an immutable saved comment. Requires explicit intent and current documentId, revision, comment ID/hash. holeSpacingMm is an absolute distance in mm: the two Z-axis holes move to X=±spacing/2, Y=0. Plate dimensions, hole diameter and bottom Z=0 stay unchanged. Rejects touching/intersecting holes or edges. Validates exact hole locations and STEP before publishing; unchanged spacing returns changed:false without a revision. Undo restores the prior spacing.',
  inputSchema:z.strictObject({documentId:z.string().min(1),expectedRevision:z.string().regex(/^r[1-9][0-9]*$/),
    commentId:z.string().uuid(),sha256:z.string().regex(/^[a-f0-9]{64}$/),holeSpacingMm:z.number().positive()}),
  annotations:{destructiveHint:false,openWorldHint:false},
}, input=>request('/api/geometry/plate-hole-spacing',input));
server.registerTool('sync_cad_snapshot', {
  description:'Publish an already exported FreeCAD single-solid or CyberTrack assembly snapshot from the server-configured CAD inbox. get_state.cadBridge provides adapterScript (single solid), assemblyAdapterScript (whole model), and inbox paths. Native assembly previews do not claim STEP validation. Use the existing FreeCAD MCP with the matching adapter to export/edit/restore the native document first. Single-solid STEP mapping or assembly mesh hashes, source identity, target and unchanged surrounding parts are validated before commit. attach requires an empty document; refresh publishes an external change; edit requires immutable comment ID/hash; undo requires the latest operation ID and an actual native restore. Inputs never accept filesystem paths. Read get_state after an uncertain response; if its cadSnapshotId matches, do not repeat the edit.',
  inputSchema:z.strictObject({documentId:z.string().min(1),expectedRevision:z.string().regex(/^r[1-9][0-9]*$/),
    snapshotId:z.string().regex(/^[a-zA-Z0-9_-]{1,128}$/),mode:z.enum(['attach','refresh','edit','undo']),
    commentId:z.string().uuid().optional(),sha256:z.string().regex(/^[a-f0-9]{64}$/).optional(),operationId:z.string().regex(/^r[1-9][0-9]*$/).optional()}),
  annotations:{destructiveHint:false,openWorldHint:false},
},input=>request('/api/cad/sync',input));
registerAppTool(server, 'open_model', {
  description: 'Open the independent interactive CAD comment prototype in this conversation. Select a part or surface and send a structured comment to the active conversation. Requires the local prototype service on port 9473.',
  inputSchema: {}, annotations: readOnly,
  _meta: { ui: { resourceUri: uri }, 'openai/outputTemplate': uri, 'openai/ui': { entrypoints: [{ type: 'thread' }] } },
}, () => request('/api/state?preview=gzip'));
server.registerTool('get_state', { description: 'Read model and saved comment snapshots with real agent receipts.', inputSchema: {geometryKey:z.string().max(128).optional()}, annotations: readOnly }, input => request('/api/state?preview=gzip'+(input.geometryKey?'&geometryKey='+encodeURIComponent(input.geometryKey):'')));
server.registerTool('save_comment', { description: 'Save a validated immutable comment snapshot. This alone does not send a chat message.', inputSchema: { payload: z.record(z.string(), z.unknown()) }, annotations: { destructiveHint: false, openWorldHint: false } }, ({ payload }) => request('/api/comments', payload));
server.registerTool('acknowledge_comment', { description: 'After actually reading a comment, record the current agent understanding. Never claim geometry edits that have not occurred.', inputSchema: { id: z.string().uuid(), sha256: z.string().regex(/^[a-f0-9]{64}$/), message: z.string().min(1).max(1500) }, annotations: { destructiveHint: false, openWorldHint: false } }, input => request('/api/receipt', input));
server.registerTool('apply_center_hole', {
  description: 'Actually create or resize a centered Z-axis through-hole in the cylinder targeted by a saved comment. Uses OpenCascade boolean solid geometry, validates STEP round-trip, commits a new immutable revision and updates live previews. Only call after the user authorizes the edit and specifies diameter. The comment must match expectedRevision. Other parts remain unchanged.',
  inputSchema: { documentId:z.string().min(1),commentId:z.string().uuid(), sha256:z.string().regex(/^[a-f0-9]{64}$/), expectedRevision:z.string().regex(/^r[1-9][0-9]*$/), diameterMm:z.number().positive() },
  annotations: {destructiveHint:false,openWorldHint:false},
}, input=>request('/api/geometry/center-hole',input));
registerAppResource(server, 'cad-model', uri, {}, async () => ({ contents: [{ uri, mimeType: RESOURCE_MIME_TYPE, text: await readFile(new URL('./model.html', import.meta.url), 'utf8'), _meta: { ui: { prefersBorder: true, csp: { connectDomains: [], resourceDomains: [] } } } }] }));
await server.connect(new StdioServerTransport());
