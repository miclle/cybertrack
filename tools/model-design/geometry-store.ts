import type { Model, Comments, HoleRequest, GeometrySummary, Geometry, Preview } from './types.js';
import { spawn } from 'node:child_process';
import { readFile, mkdir } from 'node:fs/promises';
import { join } from 'node:path';
import { randomUUID } from 'node:crypto';
import { validateEditComment } from './model.js';

export function validateHoleRequest(input: HoleRequest, model: Model, comments: Comments) {
  const {comment,part}=validateEditComment(input,model,comments);
  function fail(message: string, status = 400): never { throw Object.assign(new Error(message), { status }); }
  if (!part || part.kind !== 'cylinder') fail('当前只支持圆柱零件的中心 Z 轴贯通孔。');
  if (typeof input.diameterMm !== 'number' || !Number.isFinite(input.diameterMm) || input.diameterMm <= 0 || input.diameterMm >= part.radius*2) fail('孔径必须大于 0 且小于零件外径。');
  if (part.centerHoleDiameter === input.diameterMm) fail('该孔径已经应用。',409);
  return {comment,part};
}

export async function buildGeometry(root: string, model: Model, dataRoot = join(root,'.data')): Promise<Geometry> {
  if(model.parts.some(part=>(part.kind==='step' || part.kind==='native'))) throw new Error('外部 CAD 模型只能在原生文档中修改。');
  return runGeometry(root,model.revision,dataRoot,'geometry.py',{model});
}
export async function runGeometry(root: string, revision: string, dataRoot: string, script: string, request: object): Promise<Geometry> {
  const key=`${revision}-${randomUUID()}`;
  const output=join(dataRoot,'geometry',key);
  await mkdir(join(dataRoot,'geometry'),{recursive:true});
  const summary=await new Promise<GeometrySummary>((resolve,reject)=>{
    const child=spawn(join(root,'.venv','bin','python'),[join(root,script)],{stdio:['pipe','pipe','pipe']});
    let stdout='',stderr='';
    const timer=setTimeout(()=>{child.kill();reject(new Error('几何计算超时，模型未改变。'));},60000);
    child.on('error',error=>{clearTimeout(timer);reject(error);});
    child.stdout.on('data',b=>{stdout+=b;});child.stderr.on('data',b=>{stderr+=b;});
    child.on('close',code=>{clearTimeout(timer);if(code!==0)return reject(new Error(`几何计算失败：${stderr.slice(-1500)}`));try{resolve(JSON.parse(stdout.trim().split('\n').at(-1) || ''));}catch{reject(new Error('几何结果无效。'));}});
    child.stdin.end(JSON.stringify({...request,revision,output}));
  });
  return {...summary,key};
}
export async function readPreview(root: string,model: Model,dataRoot = join(root,'.data')): Promise<Preview>{return JSON.parse(await readFile(join(dataRoot,'geometry',requireGeometry(model).key,'preview.json'),'utf8'));}

export function requireGeometry(model: Model): Geometry {
  if (!model.geometry) throw new Error('模型缺少已验证的几何产物。');
  return model.geometry;
}
