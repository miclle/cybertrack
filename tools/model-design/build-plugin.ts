import { build } from 'esbuild';
import { resolve } from 'node:path';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
const root=resolve(import.meta.dirname,'..');
const plugin=process.argv.includes('--plugin');
const output=resolve(root,plugin ? 'plugin/dist' : 'dist/web');
await mkdir(output,{recursive:true});
const ui=await build({
  absWorkingDir:root, entryPoints:['app.ts'], bundle:true, format:'esm', target:'es2022',
  platform:'browser', write:false, minify:true,
  define: plugin ? {} : {'globalThis.__MCP_APP__':'false'},
  plugins: plugin ? [{name:'mcp-only-transport',setup(builder) {
    builder.onResolve({filter:/^\.\/transport\.js$/},()=>({path:resolve(root,'mcp-transport.ts')}));
  }}] : [],
});
const javascript=ui.outputFiles?.[0]?.text;
if (!javascript) throw new Error('UI 构建未生成 JavaScript。');
if (!plugin) {
  await writeFile(resolve(output,'app.js'),javascript);
} else {
  let html=await readFile(resolve(root,'index.html'),'utf8');
  html=html.replace('<link rel="stylesheet" href="/style.css">',`<style>${await readFile(resolve(root,'style.css'),'utf8')}</style>`)
    .replace('<script type="module" src="/app.js"></script>',()=>`<script type="module">${javascript.replaceAll('</script','<\\/script')}</script>`);
  await writeFile(resolve(output,'model.html'),html);
  await build({absWorkingDir:root,entryPoints:['mcp-server.ts'],outfile:resolve(output,'mcp-server.mjs'),bundle:true,
    platform:'node',target:'node24',format:'esm',packages:'bundle',
    banner:{js:"import { createRequire } from 'node:module'; const require = createRequire(import.meta.url);"}});
}
