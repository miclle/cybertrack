// Integration check with real FreeCAD exports; synthetic comment, no desktop UI claim.
import assert from 'node:assert/strict';
import {readFile, writeFile, mkdir} from 'node:fs/promises';
import {resolve, join} from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';
import {createHash, randomUUID} from 'node:crypto';
import {execFileSync} from 'node:child_process';

const root = resolve(fileURLToPath(new URL('..', import.meta.url)));
if (process.argv.length !== 3) throw Error('Usage: node scripts/check_solidcue_sync.mjs <native-study-directory>');
const study = resolve(process.argv[2]);
const lock = JSON.parse(await readFile(join(root, 'tools/solidcue/lock.json'), 'utf8'));
const upstream = join(root, lock.source_directory);
assert.equal(execFileSync('git', ['rev-parse', 'HEAD'], {cwd: upstream, encoding: 'utf8'}).trim(), lock.revision);
assert.equal(execFileSync('git', ['status', '--porcelain'], {cwd: upstream, encoding: 'utf8'}).trim(), '');
const {blankModel, validateComment} = await import(pathToFileURL(join(upstream, 'dist/model.js')));
const {prepareCadSync} = await import(pathToFileURL(join(upstream, 'dist/cad-bridge.js')));
const {operationHistory} = await import(pathToFileURL(join(upstream, 'dist/history.js')));
const inbox = join(study, 'cad-inbox'), data = join(study, 'sync-check-' + randomUUID());
await mkdir(data);
let model = blankModel('cybertrack-native-check');
const revisions = new Map([[model.revision, model]]), comments = new Map();
const sync = async input => {
  model = await prepareCadSync({documentId: model.documentId, expectedRevision: model.revision, ...input},
    model, comments, revisions, upstream, data, inbox);
  revisions.set(model.revision, model);
};
await sync({snapshotId: 'baseline', mode: 'attach'});
const original = model;
const preview = JSON.parse(await readFile(join(data, 'geometry', model.geometry.key, 'preview.json')));
assert.equal(preview.meshes['external-01'].faces.length, 6);
const payload = validateComment({documentId: model.documentId, revision: model.revision,
  selection: {kind: 'object', objectId: 'external-01'},
  camera: {position: [0, 0, 100], target: [0, 0, 0]},
  comment: '集成测试：Length 从 5 改为 6 mm，其余属性保持。'}, model, preview);
const comment = {id: randomUUID(), sha256: createHash('sha256').update(JSON.stringify(payload)).digest('hex'), payload, receipt: null};
comments.set(comment.id, comment);
await assert.rejects(() => prepareCadSync({documentId: model.documentId, expectedRevision: 'r1', snapshotId: 'edit',
  mode: 'edit', commentId: comment.id, sha256: comment.sha256}, model, comments, revisions, upstream, data, inbox));
await sync({snapshotId: 'edit', mode: 'edit', commentId: comment.id, sha256: comment.sha256});
assert.equal(model.parts[0].properties.Length, 6);
const editRevision = model.revision;
await sync({snapshotId: 'restored', mode: 'undo', operationId: editRevision});
assert.deepEqual(model.parts[0].properties, original.parts[0].properties);
assert.equal(operationHistory(revisions).entries.find(e => e.id === editRevision).status, 'undone');
const sourceManifest = JSON.parse(await readFile(join(study, 'provenance.json')));
assert.equal(createHash('sha256').update(await readFile(join(root, sourceManifest.source))).digest('hex'), sourceManifest.source_sha256);
const report = {scope: 'native STEP plus SolidCue sync integration; synthetic comment; no actual desktop card',
  upstream_revision: lock.revision, source_object: sourceManifest.source_object,
  baseline_revision: original.revision, edit_revision: editRevision, restored_revision: model.revision,
  face_mapping_count: preview.meshes['external-01'].faces.length, stale_revision_rejected: true,
  source_file_preserved: true, restored_properties: model.parts[0].properties,
  restored_volume_mm3: model.geometry.parts['external-01'].volumeMm3};
await writeFile(join(study, 'sync-verification.json'), JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
