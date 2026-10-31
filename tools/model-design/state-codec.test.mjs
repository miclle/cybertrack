import {test} from 'node:test';
import assert from 'node:assert/strict';
import {gzipSync} from 'node:zlib';
import {decodeState,geometryKey} from './dist/state-codec.js';
test('compressed preview and cache reuse stay bound to exact geometry revision',async()=>{
 const preview={revision:'r2',engine:'native',parts:{},meshes:{}},model={revision:'r2',geometry:{key:'r2-unique'}};
 const wire={model,previewCompressed:{encoding:'gzip-base64',data:gzipSync(JSON.stringify(preview)).toString('base64')}};
 const result=await decodeState(wire);assert.deepEqual(result.preview,preview);assert.equal(geometryKey(),'r2-unique');
 assert.strictEqual((await decodeState({model,previewUnchanged:true})).preview,result.preview);
 await assert.rejects(()=>decodeState({model:{revision:'r3',geometry:{key:'r3-new'}},previewUnchanged:true}),/缓存/);
 await assert.rejects(()=>decodeState({...wire,model:{...model,revision:'r3'}}),/版本/);
 await assert.rejects(()=>decodeState({model:{...model,revision:'r3'},previewUnchanged:true}),/缓存/);
});
