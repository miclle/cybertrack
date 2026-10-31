// Wire and journal shapes stay compatible with the existing cad-comment/v1 data.
export type Vector3 = [number, number, number];
export type Surface = '+X' | '-X' | '+Y' | '-Y' | '+Z' | '-Z' | 'cylindrical-wall';
interface PartBase { id: string; name: string; position: Vector3; color: string }
export interface BoxPart extends PartBase { kind: 'box'; profile?: undefined; size: Vector3 }
export interface CylinderPart extends PartBase {
  kind: 'cylinder'; profile?: undefined; radius: number; height: number; centerHoleDiameter?: number;
}
export interface SpacerPart extends PartBase {
  kind: 'cylinder'; profile: 'spacer'; radius: number; height: number; centerHoleDiameter: number;
}
export interface PlatePart extends PartBase {
  kind: 'box'; profile: 'mounting-plate'; size: Vector3; holeDiameter: number; holeSpacing: number;
}
export interface CadSource {
  application: 'FreeCAD'; documentName: string; documentUid: string; objectName: string; fingerprint: string;
}
export interface ExternalPart extends PartBase {
  kind: 'step'; profile?: undefined; source: CadSource; properties: Record<string,number>;
}
export interface NativePart extends PartBase {
  kind: 'native'; profile?: undefined; source: CadSource; properties: Record<string,number>; meshSha256: string;
}
export type Part = BoxPart | CylinderPart | SpacerPart | PlatePart | ExternalPart | NativePart;
export interface ObjectSelection { kind: 'object'; objectId: string; objectName: string }
export interface SurfaceSelection {
  kind: 'surface'; objectId: string; objectName: string; surface: Surface; triangleIndex: number;
  faceId?: string;
  worldPoint: Vector3; localPoint: Vector3; worldNormal: Vector3;
}
export type Selection = ObjectSelection | SurfaceSelection;
export interface CommentInput {
  documentId: string; revision: string;
  selection: (Omit<ObjectSelection, 'objectName'> | Omit<SurfaceSelection, 'objectName'>) & {objectName?: string};
  camera: { position: Vector3; target: Vector3 }; comment: string;
}
export interface CommentPayload extends CommentInput {
  selection: Selection;
  schema: 'cad-comment/v1'; unit: 'mm'; upAxis: 'Z'; objectParameters: Part;
}
export interface Receipt { receivedAt: string; message: string; receiver: string }
export interface Processing {
  status: 'processing' | 'completed' | 'failed'; revision?: string; changed?: boolean;
  message?: string; updatedAt?: string;
}
export interface Delivery {
  status: 'queued' | 'uncertain'; transport?: 'codex-cli-queue'; threadId?: string;
  messageId?: string; queuedAt?: string; attemptedAt?: string;
}
export interface CommentRecord {
  id: string; createdAt: string; payload: CommentPayload; sha256: string; receipt: Receipt | null;
  processing?: Processing; delivery?: Delivery;
}
export interface DocumentRequest { documentId: string; expectedRevision: string }
export interface EditRequest extends DocumentRequest { commentId: string; sha256: string }
export interface SpacerRequest extends DocumentRequest {
  requestId: string; outerDiameterMm: number; holeDiameterMm: number; heightMm: number;
}
export interface PlateRequest extends DocumentRequest {
  requestId: string; lengthMm: number; widthMm: number; thicknessMm: number;
  holeDiameterMm: number; holeSpacingMm: number;
}
export type SpacerDimensions = Pick<SpacerRequest, 'outerDiameterMm' | 'holeDiameterMm' | 'heightMm'>;
export interface SpacerUpdate extends EditRequest, Partial<SpacerDimensions> {}
export interface PlateUpdate extends EditRequest { holeSpacingMm: number }
export interface HoleRequest extends EditRequest { diameterMm: number }
export interface UndoRequest extends DocumentRequest { operationId: string }
interface OperationBase { objectId: string; previousRevision: string; createdAt: string }
export type Operation = OperationBase & (
  | { type: 'create-spacer'; request: SpacerRequest }
  | { type: 'create-mounting-plate'; request: PlateRequest }
  | { type: 'center-through-hole'; commentId: string; diameterMm: number }
  | { type: 'update-spacer-parameters'; commentId: string; parameters: Partial<SpacerDimensions> }
  | { type: 'update-plate-hole-spacing'; commentId: string; parameters: { holeSpacingMm: number } }
  | { type: 'sync-cad'; snapshotId: string; mode: 'attach'|'refresh'|'edit'; commentId?: string; before: Record<string,number>; after: Record<string,number> }
  | { type: 'undo'; undoOf: string; restoredRevision: string; snapshotId?: string }
);
export interface PartGeometry {
  valid: boolean; solids: number; volumeMm3: number; faces: number; boundsMm: number[];
  stepRoundTripValid: boolean; stepBoundsVerified: boolean;
  holeDiameterMm?: number; holeSpacingMm?: number; holeDepthMm?: number;
  holeCentersMm?: [number, number][]; axis?: 'Z'; localCenter?: [number, number];
  holeGeometryVerified?: boolean; axisVoidVerified?: boolean; wallSolidVerified?: boolean;
  removedVolumeMm3?: number; bottomAnchoredVerified?: boolean;
  stepHoleGeometryVerified?: boolean; stepHoleVoidVerified?: boolean; stepWallSolidVerified?: boolean;
}
export interface GeometrySummary { revision: string; engine: string; parts: Record<string, PartGeometry> }
export interface Geometry extends GeometrySummary { key: string }
export interface PreviewFace { id: string; type: string; start: number; count: number }
export interface PreviewMesh { positions: number[]; indices: number[]; faces?: PreviewFace[] }
export interface Preview extends GeometrySummary {
  meshes: Record<string, PreviewMesh>;
}
// Prepared revisions do not have geometry until the kernel and STEP checks succeed.
export interface CadSyncRequest extends DocumentRequest {
  snapshotId: string; mode: 'attach'|'refresh'|'edit'|'undo'; commentId?: string; sha256?: string; operationId?: string;
}
export interface Model {
  documentId: string; revision: string; unit: 'mm'; upAxis: 'Z'; name: string;
  parts: Part[]; cadSnapshotId?: string; sceneFingerprint?: string; lastOperation?: Operation; geometry?: Geometry;
}
export type Revisions = Map<string, Model>;
export type Comments = Map<string, CommentRecord>;
export interface HistoryEntry {
  id: string; type: Operation['type']; objectId: string; objectName?: string;
  commentId: string | null; requestId: string | null;
  beforeParameters: Part | null; afterParameters: Part | null;
  previousRevision: string; revision: string; createdAt: string; undoOf: string | null;
  beforeDiameterMm: number; afterDiameterMm: number;
  beforeVolumeMm3?: number; afterVolumeMm3?: number; status: 'applied' | 'undone';
}
export interface History { entries: HistoryEntry[]; undoOperationId: string | null }
export interface StepCatalogEntry { revision: string; parts: { id: string; name: string }[] }
export interface StepRequest { documentId: string; revision: string; partId: string }
export interface StepArtifact extends StepRequest {
  filename: string; byteLength: number; sha256: string;
  resource: { uri: string; mimeType: string; blob: string };
}
export interface SavedStep extends Omit<StepArtifact, 'resource'> { filePath: string; reused: boolean; saved: true }
export type DownloadResult = (Omit<StepArtifact, 'resource'> | SavedStep) & { message: string };
export interface State {
  model: Model; preview: Preview; history: History; editing: boolean; revisions: string[];
  stepExports: StepCatalogEntry[]; comments: CommentRecord[];
  cadBridge?: { adapterScript: string; assemblyAdapterScript?: string; inbox: string };
  transport: 'agent-pull' | 'codex-cli-queue'; targetThreadId: string | null; nativeMessageBridge: boolean;
}
export type JournalEvent =
  | { type: 'geometry-model'; model: Model }
  | { type: 'comment'; record: CommentRecord }
  | { type: 'delivery'; id: string; delivery: Delivery }
  | { type: 'processing'; id: string; processing: Processing }
  | { type: 'receipt'; id: string; receipt: Receipt };
export interface UndoResult { revision: string; operation: Operation; history: History }
export interface Api {
  '/api/state': { input: undefined; output: State };
  '/api/comments': { input: CommentInput; output: CommentRecord };
  '/api/geometry/undo': { input: UndoRequest; output: UndoResult };
  '/api/export-step': { input: StepRequest; output: StepArtifact };
  '/api/send': { input: { id: string; sha256: string }; output: Delivery };
}
export type ApiPath = keyof Api;
