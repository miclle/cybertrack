import { errorCode } from './errors.js';
import { requireGeometry } from './geometry-store.js';
import type { Model, Revisions, StepRequest, StepArtifact, SavedStep, StepCatalogEntry } from './types.js';
import { open, mkdir, writeFile, readFile, link, unlink } from 'node:fs/promises';
import { join } from 'node:path';
import { createHash, randomUUID } from 'node:crypto';
import { validateDocument } from './model.js';

export function stepCatalog(revisions: Revisions): StepCatalogEntry[] {
  return [...revisions.values()].map(version => ({
    revision: version.revision,
    parts: version.parts.filter(part=>part.kind!=='native').map(({ id, name }) => ({ id, name })),
  }));
}

// Read committed artifacts only. Export never builds geometry or changes the journal.
export async function exportStep(input: StepRequest, model: Model, revisions: Revisions, dataRoot: string): Promise<StepArtifact> {
  validateDocument(input, model);
  if (Object.keys(input).some(key => !['documentId', 'revision', 'partId'].includes(key)) ||
      !/^r[1-9][0-9]*$/.test(input.revision) ||
      typeof input.partId !== 'string' || !/^[a-zA-Z0-9_-]+$/.test(input.partId)) {
    throw new Error('需要明确的版本和零件 ID。');
  }
  const version = revisions.get(input.revision);
  if (!version || version.documentId !== model.documentId) throw new Error('指定版本不存在。');
  if (!version.parts.length) throw new Error('空白版本没有 STEP 产物。');
  if (input.partId !== 'assembly' && !version.parts.some(part => part.id === input.partId)) {
    throw new Error('指定版本中没有这个零件。');
  }
  if(version.parts.some(part=>part.kind==='native')) throw new Error('整机为原生 CAD 预览，请从 FreeCAD 导出 STEP。');
  const handle = await open(join(dataRoot, 'geometry', requireGeometry(version).key, `${input.partId}.step`), 'r');
  let bytes;
  try {
    if ((await handle.stat()).size > 8 * 1024 * 1024) throw new Error('STEP 超过当前内嵌下载的 8 MiB 上限。');
    bytes = await handle.readFile();
  } finally { await handle.close(); }
  const documentTag = createHash('sha256').update(model.documentId).digest('hex').slice(0, 12);
  const filename = `solidcue-${documentTag}-${input.revision}-${input.partId}.step`;
  return {
    documentId: model.documentId, revision: input.revision, partId: input.partId,
    filename, byteLength: bytes.length, sha256: createHash('sha256').update(bytes).digest('hex'),
    resource: { uri: `file:///${filename}`, mimeType: 'application/step', blob: bytes.toString('base64') },
  };
}

export async function saveStep(input: StepRequest, model: Model, revisions: Revisions, dataRoot: string, exportRoot: string): Promise<SavedStep> {
  const {resource,...artifact}=await exportStep(input,model,revisions,dataRoot);
  const bytes=Buffer.from(resource.blob,'base64');
  await mkdir(exportRoot,{recursive:true});
  const filePath=join(exportRoot,artifact.filename);
  const temporary=join(exportRoot,`.solidcue-${randomUUID()}.tmp`);
  let reused=false;
  await writeFile(temporary,bytes,{flag:'wx'});
  try {
    try {await link(temporary,filePath);}
    catch(error) {
      if(errorCode(error)!=='EEXIST') throw error;
      reused=true;
    }
    const actual=await readFile(filePath);
    if(createHash('sha256').update(actual).digest('hex')!==artifact.sha256) {
      throw new Error('导出目录存在同名但内容不同的文件，未覆盖；请先处理该文件。');
    }
    return {...artifact,filePath,reused,saved:true};
  } finally {await unlink(temporary);}
}
