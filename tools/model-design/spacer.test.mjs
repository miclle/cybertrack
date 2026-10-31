import {test} from 'node:test';
import assert from 'node:assert/strict';
import {blankModel} from './dist/model.js';
import {spacerRequest,prepareSpacer,prepareSpacerUpdate} from './dist/spacer.js';
import {operationHistory,prepareUndo} from './dist/history.js';

const model=blankModel('spacer-test');
const input={documentId:model.documentId,expectedRevision:'r1',requestId:'create-01',outerDiameterMm:20,holeDiameterMm:6.5,heightMm:12};
test('spacer creation records intent and anchors the bottom; undo restores an empty model',()=>{
  const created=prepareSpacer(spacerRequest(input,model),model);
  assert.deepEqual(created.parts[0].position,[0,0,6]);
  assert.equal(created.parts[0].radius,10);
  assert.equal(created.parts[0].centerHoleDiameter,6.5);
  assert.deepEqual(created.lastOperation.request,input);
  const revisions=new Map([['r1',model],['r2',created]]);
  assert.throws(()=>prepareUndo({documentId:'wrong',expectedRevision:'r2',operationId:'r2'},created,revisions),/文档/);
  const undone=prepareUndo({documentId:model.documentId,expectedRevision:'r2',operationId:'r2'},created,revisions);
  revisions.set('r3',undone);
  assert.deepEqual(undone.parts,[]);
  const history=operationHistory(revisions);
  assert.equal(history.undoOperationId,null);
  assert.equal(history.entries[0].beforeParameters,null);
  assert.equal(history.entries[0].status,'undone');
  assert.equal(history.entries[1].objectName,'隔离垫套');
  assert.equal(history.entries[1].afterParameters,null);
});

test('spacer edits keep the bottom fixed, preserve omitted dimensions and undo exact parameters',()=>{
  const created=prepareSpacer(input,model);
  const comment={id:'comment',sha256:'hash',payload:{documentId:model.documentId,revision:'r2',selection:{objectId:'spacer-01'}}};
  const comments=new Map([[comment.id,comment]]);
  const edit={documentId:model.documentId,expectedRevision:'r2',commentId:comment.id,sha256:comment.sha256,heightMm:16};
  const {next}=prepareSpacerUpdate(edit,created,comments);
  assert.deepEqual(next.parts[0],{...created.parts[0],height:16,position:[0,0,8]});
  assert.deepEqual(created.parts[0].position,[0,0,6]);
  const revisions=new Map([['r1',model],['r2',created],['r3',next]]);
  const restored=prepareUndo({documentId:model.documentId,expectedRevision:'r3',operationId:'r3'},next,revisions);
  assert.deepEqual(restored.parts,created.parts);
  assert.equal(prepareSpacerUpdate({...edit,heightMm:12},created,comments).next,null);
  const resized=prepareSpacerUpdate({...edit,outerDiameterMm:24,holeDiameterMm:8},created,comments).next.parts[0];
  assert.deepEqual([resized.radius,resized.centerHoleDiameter,resized.height,resized.position[2]],[12,8,16,8]);
  for (const patch of [{documentId:'other'},{sha256:'bad'},{commentId:'missing'},{expectedRevision:'r1'},
    {heightMm:undefined},{heightMm:null},{heightMm:Infinity},{heightMm:'16'},{heightMm:0},{heightMm:-4},
    {holeDiameterMm:20},{outerDiameterMm:6},{script:'code'}]) {
    assert.throws(()=>prepareSpacerUpdate({...edit,...patch},created,comments));
  }
  const {heightMm,...missing}=edit;
  assert.throws(()=>prepareSpacerUpdate(missing,created,comments),/至少/);
  for (const payload of [
    {...comment.payload,documentId:'other'},
    {...comment.payload,revision:'r1'},
    {...comment.payload,selection:{objectId:'missing'}},
  ]) assert.throws(()=>prepareSpacerUpdate(edit,created,new Map([[comment.id,{...comment,payload}]])));
  const other=structuredClone(created);delete other.parts[0].profile;
  assert.throws(()=>prepareSpacerUpdate(edit,other,comments),/隔离垫套/);
  comment.processing={status:'completed'};
  assert.throws(()=>prepareSpacerUpdate(edit,created,comments),/已经应用/);
});
test('spacer boundary rejects invalid dimensions, unknown fields, stale and wrong documents',()=>{
  for(const key of ['outerDiameterMm','holeDiameterMm','heightMm']) {
    for(const value of [0,-1,NaN,Infinity,'12',null]) assert.throws(()=>spacerRequest({...input,[key]:value},model));
  }
  for(const patch of [{documentId:'other'},{documentId:undefined},{requestId:''},{script:'arbitrary'},{holeDiameterMm:20},{holeDiameterMm:21}]) {
    assert.throws(()=>spacerRequest({...input,...patch},model));
  }
  assert.throws(()=>prepareSpacer({...input,expectedRevision:'r2'},model),/空白/);
  assert.throws(()=>prepareSpacer({...input,expectedRevision:'r2'},prepareSpacer(input,model)),/空白/);
});
