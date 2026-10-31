import type { CommentRecord, Delivery } from './types.js';
import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
const run = promisify(execFile);
export async function queueComment(record: CommentRecord, threadId: string | undefined, runner: (command: string, args: string[], options: {timeout: number; maxBuffer: number}) => Promise<{stdout: string}> = run): Promise<Delivery> {
  if (!threadId || !/^[a-f0-9-]{36}$/.test(threadId)) throw new Error('未绑定当前对话，不能发送。');
  const message = `来自独立 SolidCue 页面的评论，请直接处理并写回回执。\n这是用户已授权的当前对话投递。先核对以下快照，然后调用插件 acknowledge_comment；若本回合尚无插件工具，可 POST http://127.0.0.1:9473/api/receipt，字段 id、sha256、message。回执必须描述实际理解，仅描述实际执行结果，未经几何工具确认不得声称模型已修改。不要再次投递此消息。\n${JSON.stringify(record, null, 2)}`;
  const { stdout } = await runner('codex', ['queue', '--thread', threadId, '--message', message], { timeout: 15000, maxBuffer: 16384 });
  const match = stdout.match(/Queued message ([\w-]+) for thread ([\w-]+)/);
  if (!match || match[2] !== threadId) throw new Error('投递结果不明确，勿自动重发。');
  return { status: 'queued', transport: 'codex-cli-queue', threadId, messageId: match[1], queuedAt: new Date().toISOString() };
}
