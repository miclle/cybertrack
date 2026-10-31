import { test } from 'node:test';
import assert from 'node:assert/strict';
import { model, validateComment } from './dist/model.js';
const input = () => ({ documentId: model.documentId, revision: 'r1', selection: { kind: 'surface', objectId: 'pin-01', objectName: '伪造名称', surface: '+Z', triangleIndex: 4, worldPoint: [-30,0,38], localPoint: [0,0,15], worldNormal: [0,0,1] }, camera: { position:[190,250,180], target:[0,0,27] }, comment:'增高到 40 mm' });
test('uses authoritative identity and retains geometry snapshot', () => { const result = validateComment(input()); assert.equal(result.selection.objectName, '定位柱'); assert.equal(result.objectParameters.height, 30); assert.deepEqual(result.selection.worldPoint, [-30,0,38]); assert.equal(result.unit, 'mm'); });
test('rejects stale model revision', () => { assert.throws(() => validateComment({...input(),revision:'r0'}), /版本/); });
test('rejects invalid surface coordinates and missing object', () => { const value = input(); value.selection.worldPoint[0] = Infinity; assert.throws(() => validateComment(value), /位置/); value.selection.objectId = 'missing'; assert.throws(() => validateComment(value), /零件/); });
test('whole-object selection does not invent a hit point', () => { const value = input(); value.selection = {kind:'object',objectId:'base-01',worldPoint:[0,0,0]}; const result = validateComment(value); assert.equal(result.selection.worldPoint, undefined); });
test('rejects blank comments and invalid camera', () => { assert.throws(() => validateComment({...input(),comment:'  '}), /评论/); assert.throws(() => validateComment({...input(),camera:{}}), /视角/); });

test('CAD face references are bound to the exact preview triangle range', () => {
  const value=input(); value.selection.faceId='Face2';
  const preview={meshes:{'pin-01':{faces:[{id:'Face2',type:'PLANE',start:3,count:2}]}}};
  assert.equal(validateComment(value,model,preview).selection.faceId,'Face2');
  assert.throws(()=>validateComment(value,model),/面引用/);
  assert.throws(()=>validateComment({...value,selection:{...value.selection,triangleIndex:5}},model,preview),/面引用/);
  assert.throws(()=>validateComment({...value,selection:{...value.selection,faceId:'Face1'}},model,preview),/面引用/);
});
