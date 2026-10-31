import {test} from 'node:test';
import assert from 'node:assert/strict';
import {validateHoleRequest} from './dist/geometry-store.js';
import {model} from './dist/model.js';
const comment={id:'comment',sha256:'hash',payload:{documentId:model.documentId,revision:'r1',selection:{objectId:'knob-01'}}};
const comments=new Map([[comment.id,comment]]);
const input={documentId:model.documentId,commentId:'comment',sha256:'hash',expectedRevision:'r1',diameterMm:8};
test('hole operation resolves target from saved comment and accepts positive fitting diameter',()=>{
  assert.equal(validateHoleRequest(input,model,comments).part.id,'knob-01');
});
test('stale revision and mismatched comment cannot mutate a model',()=>{
  for(const patch of [{expectedRevision:'r2'},{sha256:'bad'},{commentId:'missing'}]) assert.throws(()=>validateHoleRequest({...input,...patch},model,comments));
  assert.throws(()=>validateHoleRequest({...input,expectedRevision:'r2'},{...model,revision:'r2'},comments),/旧版本/);
});
test('invalid or oversized diameters are rejected',()=>{
  for(const diameterMm of [0,-1,36,50,NaN,Infinity,'8']) assert.throws(()=>validateHoleRequest({...input,diameterMm},model,comments));
});
