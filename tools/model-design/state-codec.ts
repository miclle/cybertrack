import type {State,Preview} from './types.js';
let cached: {key:string;preview:Preview}|undefined;
export const geometryKey=()=>cached?.key;
export async function decodeState(value:unknown):Promise<State>{
  const state=value as State & {previewCompressed?:{encoding:string;data:string};previewUnchanged?:boolean};
  const key=state.model.geometry?.key;
  if(state.previewUnchanged){
    if(!cached || cached.key!==key || cached.preview.revision!==state.model.revision)throw new Error('预览缓存与模型版本不匹配');
    return {...state,preview:cached.preview};
  }
  let preview=state.preview;
  if(state.previewCompressed){
    if(state.previewCompressed.encoding!=='gzip-base64')throw new Error('未知预览编码');
    const bytes=Uint8Array.from(atob(state.previewCompressed.data),c=>c.charCodeAt(0));
    const stream=new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'));
    const reader=stream.getReader(),chunks:Uint8Array[]=[];let size=0;
    for(;;){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>128*1024*1024){await reader.cancel();throw new Error('预览解压超过限制');}chunks.push(value);}
    preview=JSON.parse(await new Blob(chunks as BlobPart[]).text()) as Preview;
  }
  if(!preview || preview.revision!==state.model.revision)throw new Error('预览与模型版本不匹配');
  if(key)cached={key,preview};
  return {...state,preview};
}
