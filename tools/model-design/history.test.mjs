import {test} from 'node:test';
import assert from 'node:assert/strict';
import {operationHistory,prepareUndo} from './dist/history.js';
const version=(revision,hole,op)=>({documentId:'test-doc',revision,parts:[{id:'knob',name:'Knob',centerHoleDiameter:hole}],lastOperation:op});
const op=previousRevision=>({type:'center-through-hole',objectId:'knob',previousRevision});
test('undo stack supports repeated undo and a new branch without resurrecting undone edits',()=>{
  const versions=new Map([['r1',version('r1',0)],['r2',version('r2',8,op('r1'))],['r3',version('r3',10,op('r2'))]]);
  let current=versions.get('r3');
  assert.equal(operationHistory(versions).undoOperationId,'r3');
  assert.throws(()=>prepareUndo({documentId:'test-doc',expectedRevision:'r2',operationId:'r3'},current,versions),/版本/);
  assert.throws(()=>prepareUndo({documentId:'test-doc',expectedRevision:'r3',operationId:'r2'},current,versions),/最近/);
  current=prepareUndo({documentId:'test-doc',expectedRevision:'r3',operationId:'r3'},current,versions);versions.set(current.revision,current);
  assert.equal(current.parts[0].centerHoleDiameter,8);
  assert.equal(current.revision,'r4');
  assert.equal(operationHistory(versions).undoOperationId,'r2');
  const branch=version('r5',12,op('r4'));versions.set('r5',branch);
  current=prepareUndo({documentId:'test-doc',expectedRevision:'r5',operationId:'r5'},branch,versions);versions.set(current.revision,current);
  current=prepareUndo({documentId:'test-doc',expectedRevision:'r6',operationId:'r2'},current,versions);versions.set(current.revision,current);
  assert.equal(current.parts[0].centerHoleDiameter,0);
  assert.equal(operationHistory(versions).undoOperationId,null);
  assert.throws(()=>prepareUndo({documentId:'test-doc',expectedRevision:'r7',operationId:'r2'},current,versions),/最近/);
  assert.equal(versions.get('r3').parts[0].centerHoleDiameter,10);
});
test('corrupt undo chains are rejected rather than silently restoring a different edit',()=>{
  const versions=new Map([['r1',version('r1',0)],['r2',version('r2',0,{type:'undo',objectId:'knob',undoOf:'missing'})]]);
  assert.throws(()=>operationHistory(versions),/顺序/);
});
