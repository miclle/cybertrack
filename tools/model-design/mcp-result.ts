import type { CallToolResult } from '@modelcontextprotocol/sdk/types.js';
export function toolData<T>(result: CallToolResult, fallback: string): T {
  if (result.isError) {
    const content=result.content[0];
    throw new Error(content?.type==='text' ? content.text : fallback);
  }
  if (!result.structuredContent) throw new Error(fallback);
  // JSON crosses a process boundary; business validation remains in the server/kernel.
  return result.structuredContent as T;
}
