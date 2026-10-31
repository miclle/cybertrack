import type { Part, Selection, Operation, Vector3 } from '../types.js';
import { api } from '../transport.js';
import { api as mcpApi, downloadStep as mcpDownload } from '../mcp-transport.js';

// Compiled, never executed: these failures must remain visible to the type checker.
export function contractChecks(part: Part, selection: Selection, operation: Operation): void {
  if (part.kind==='cylinder') {
    part.radius.toFixed(2);
    // @ts-expect-error Cylinders do not have plate dimensions.
    part.size;
  }
  if (part.profile==='mounting-plate') {
    part.holeSpacing.toFixed(2);
    // @ts-expect-error Plates do not have a cylinder radius.
    part.radius;
  }
  if (selection.kind==='object') {
    // @ts-expect-error Whole-object selections do not invent a mesh hit point.
    selection.worldPoint;
  }
  if (operation.type==='undo') {
    operation.undoOf.toUpperCase();
    // @ts-expect-error Undo does not contain a creation request.
    operation.request;
  }
  // @ts-expect-error Spatial vectors have exactly three coordinates.
  const invalidVector: Vector3=[1,2];
  void invalidVector;
  // @ts-expect-error Undo requires the current revision and operation ID.
  void api('/api/geometry/undo',{documentId:'test'});
  // @ts-expect-error Export requires an explicit part ID in the embedded transport too.
  void mcpDownload({documentId:'test',revision:'r1'});
  // @ts-expect-error The embedded transport cannot invoke the legacy queue endpoint.
  void mcpApi('/api/send',{id:'test',sha256:'hash'});
  // @ts-expect-error Write endpoints require a payload.
  void api('/api/comments');
}
