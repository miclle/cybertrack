import { test } from 'node:test';
import assert from 'node:assert/strict';
import { queueComment } from './dist/delivery.js';
const thread = '00000000-0000-4000-8000-000000000001';
test('delivery targets exact existing thread and passes comment as an argument, not shell code', async () => {
  const record = { id: 'test', payload: { comment: '$(echo nope) `echo nope`' } };
  const result = await queueComment(record, thread, async (command, args) => {
    assert.equal(command, 'codex');
    assert.deepEqual(args.slice(0,4), ['queue','--thread',thread,'--message']);
    assert.ok(args[4].includes(record.payload.comment));
    return { stdout: `Queued message abc-123 for thread ${thread}.` };
  });
  assert.equal(result.status, 'queued');
  assert.equal(result.threadId, thread);
});
test('delivery does not accept missing binding or a different target result', async () => {
  await assert.rejects(queueComment({}, undefined), /未绑定/);
  await assert.rejects(queueComment({}, thread, async () => ({ stdout: 'Queued message abc for thread other.' })), /不明确/);
});
test('CLI failure is not reported as delivery success', async () => {
  await assert.rejects(queueComment({}, thread, async () => { throw new Error('offline'); }), /offline/);
});
