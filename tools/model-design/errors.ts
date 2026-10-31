export function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
export function errorCode(error: unknown): unknown {
  return error instanceof Error && 'code' in error ? error.code : undefined;
}
export function errorStatus(error: unknown): number {
  return error instanceof Error && 'status' in error && typeof error.status === 'number' ? error.status : 400;
}
export function fail(message: string, status = 400): never {
  throw Object.assign(new Error(message), {status});
}
export function inputObject(input: unknown): Record<string, unknown> {
  if (!input || typeof input !== 'object' || Array.isArray(input)) fail('需要 JSON 对象。');
  return input as Record<string, unknown>;
}
