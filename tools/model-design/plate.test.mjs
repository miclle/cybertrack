import {test} from 'node:test';
import assert from 'node:assert/strict';
import {blankModel} from './dist/model.js';
import {plateRequest,preparePlate,preparePlateSpacingUpdate} from './dist/plate.js';
import {operationHistory,prepareUndo} from './dist/history.js';

const blank=blankModel('plate-test');
const input={documentId:blank.documentId,expectedRevision:'r1',requestId:'plate-01',
  lengthMm:60,widthMm:30,thicknessMm:4,holeDiameterMm:6.5,holeSpacingMm:40};

test('plate creation records dimensions and undo restores the blank document name and parts',()=>{
  const created=preparePlate(plateRequest(input,blank),blank);
  assert.deepEqual(created.parts[0].size,[60,30,4]);
  assert.deepEqual(created.parts[0].position,[0,0,2]);
  assert.equal(created.parts[0].holeSpacing,40);
  assert.equal(created.parts[0].holeDiameter,6.5);
  assert.equal(created.name,'双孔安装板');
  assert.deepEqual(created.lastOperation.request,input);
  assert.deepEqual(blank.parts,[]);
  const revisions=new Map([['r1',blank],['r2',created]]);
  const undone=prepareUndo({documentId:blank.documentId,expectedRevision:'r2',operationId:'r2'},created,revisions);
  assert.equal(undone.name,blank.name);
  assert.deepEqual(undone.parts,[]);
  revisions.set('r3',undone);
  const history=operationHistory(revisions);
  assert.equal(history.undoOperationId,null);
  assert.equal(history.entries[0].status,'undone');
  assert.equal(history.entries[1].objectName,'双孔安装板');
  assert.equal(history.entries[1].afterParameters,null);
});

test('plate rejects invalid dimensions, touching holes and edges, unknown fields and stale documents',()=>{
  for(const key of ['lengthMm','widthMm','thicknessMm','holeDiameterMm','holeSpacingMm']) {
    for(const value of [0,-1,NaN,Infinity,'4',null,true,undefined])
      assert.throws(()=>plateRequest({...input,[key]:value},blank));
  }
  for(const patch of [{holeSpacingMm:6.5},{holeSpacingMm:6},{holeSpacingMm:53.5},
    {holeSpacingMm:54},{widthMm:6.5},{widthMm:6},{documentId:'other'},{requestId:''},
    {expectedRevision:'bad'},{script:'arbitrary'}]) assert.throws(()=>plateRequest({...input,...patch},blank));
  assert.throws(()=>preparePlate({...input,expectedRevision:'r2'},blank),/空白/);
  assert.throws(()=>preparePlate({...input,expectedRevision:'r2'},preparePlate(input,blank)),/空白/);
});

test('spacing edits only move the symmetric holes and undo restores exact parameters',()=>{
  const created=preparePlate(input,blank);
  const comment={id:'comment',sha256:'hash',payload:{documentId:blank.documentId,revision:'r2',selection:{objectId:'plate-01'}}};
  const comments=new Map([[comment.id,comment]]);
  const edit={documentId:blank.documentId,expectedRevision:'r2',commentId:comment.id,sha256:comment.sha256,holeSpacingMm:44};
  const {next}=preparePlateSpacingUpdate(edit,created,comments);
  assert.deepEqual(next.parts,[{...created.parts[0],holeSpacing:44}]);
  assert.equal(created.parts[0].holeSpacing,40);
  assert.deepEqual(next.lastOperation.parameters,{holeSpacingMm:44});
  assert.equal(next.lastOperation.commentId,comment.id);
  const revisions=new Map([['r1',blank],['r2',created],['r3',next]]);
  const undone=prepareUndo({documentId:blank.documentId,expectedRevision:'r3',operationId:'r3'},next,revisions);
  assert.deepEqual(undone.parts,created.parts);
  assert.equal(preparePlateSpacingUpdate({...edit,holeSpacingMm:40},created,comments).next,null);
  for(const value of [undefined,null,0,-1,'44',NaN,Infinity,true,6.5,5,53.5,54])
    assert.throws(()=>preparePlateSpacingUpdate({...edit,holeSpacingMm:value},created,comments));
  for(const patch of [{documentId:'wrong'},{expectedRevision:'r1'},{commentId:'missing'},{sha256:'wrong'},
    {lengthMm:65},{holeDiameterMm:8},{script:'code'}]) assert.throws(()=>preparePlateSpacingUpdate({...edit,...patch},created,comments));
  for(const payload of [{...comment.payload,revision:'r1'},{...comment.payload,documentId:'wrong'},
    {...comment.payload,selection:{objectId:'missing'}}])
    assert.throws(()=>preparePlateSpacingUpdate(edit,created,new Map([[comment.id,{...comment,payload}]])));
  const other=structuredClone(created);delete other.parts[0].profile;
  assert.throws(()=>preparePlateSpacingUpdate(edit,other,comments),/安装板/);
  comment.processing={status:'completed'};
  assert.throws(()=>preparePlateSpacingUpdate(edit,created,comments),/已经应用/);
});
