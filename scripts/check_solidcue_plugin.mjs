// Read-only check of the installed, pinned plugin and CyberTrack-owned service.
// SDK transport/resource checks do not constitute a native desktop card test.
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import {readFile, mkdir, writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {resolve, join} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const root=resolve(fileURLToPath(new URL('..',import.meta.url)));
const lock=JSON.parse(await readFile(join(root,'tools/solidcue/lock.json'),'utf8'));
const source=join(root,lock.source_directory);
execFileSync('python3',[join(root,'scripts/solidcue.py'),'check'],{cwd:root});
const config=JSON.parse(execFileSync('codex',['mcp','get','cad-comments','--json'],
 {encoding:'utf8',stdio:['ignore','pipe','ignore'],timeout:15000}));
assert.equal(config.enabled,true);
assert.equal(config.transport.type,'stdio');
assert.equal(config.transport.command,'node');
assert.deepEqual(config.transport.args,['./dist/mcp-server.mjs']);
assert(!config.transport.env || Object.keys(config.transport.env).length===0);
assert(!config.transport.env_vars || config.transport.env_vars.length===0);
const installed=resolve(config.transport.cwd), hashes={};
for(const file of ['.codex-plugin/plugin.json','.mcp.json','dist/mcp-server.mjs','dist/model.html']){
 const expected=await readFile(join(source,'plugin',file)),actual=await readFile(join(installed,file));
 assert.deepEqual(actual,expected,`installed bundle differs: ${file}`);
 hashes[file]=createHash('sha256').update(actual).digest('hex');
}
const require=createRequire(join(source,'package.json'));
const {Client}=await import(pathToFileURL(require.resolve('@modelcontextprotocol/sdk/client/index.js')));
const {StdioClientTransport}=await import(pathToFileURL(require.resolve('@modelcontextprotocol/sdk/client/stdio.js')));
const client=new Client({name:'cybertrack-solidcue-readonly-check',version:'1.0.0'});
const transport=new StdioClientTransport({command:config.transport.command,args:config.transport.args,cwd:installed});
try{
 await client.connect(transport);
 const {tools}=await client.listTools();
 const names=tools.map(t=>t.name).sort();
 assert.deepEqual(names,['acknowledge_comment','apply_center_hole','create_mounting_plate','create_spacer',
  'export_step','get_state','open_model','save_comment','save_step','sync_cad_snapshot','undo_model',
  'update_plate_hole_spacing','update_spacer_parameters']);
 const sync=tools.find(t=>t.name==='sync_cad_snapshot');
 assert.equal(sync.inputSchema.additionalProperties,false);
 for(const name of ['documentId','expectedRevision','snapshotId','mode'])assert(sync.inputSchema.required.includes(name));
 const open=tools.find(t=>t.name==='open_model');
 assert.equal(open.annotations.readOnlyHint,true);
 const resource=await client.readResource({uri:open._meta.ui.resourceUri});
 assert.equal(open._meta.ui.resourceUri,'ui://cad-comment/model.html');
 assert.equal(resource.contents[0].text,await readFile(join(installed,'dist/model.html'),'utf8'));
 assert.match(resource.contents[0].text,/ui\/message/);
 assert(!resource.contents[0].text.includes('/api/send'));
 const get=await client.callTool({name:'get_state',arguments:{}});
 assert(!get.isError,'get_state failed; start the CyberTrack-owned service first');
 const before=get.structuredContent;
 assert.equal(resolve(before.cadBridge.adapterScript),join(source,'freecad_bridge.py'));
 assert.equal(resolve(before.cadBridge.inbox),join(root,lock.data_directory,'cad-inbox'));
 assert.equal(before.targetThreadId,null,'service must not target a CLI conversation');
 const opened=await client.callTool({name:'open_model',arguments:{}});
 assert(!opened.isError);
 assert.deepEqual(opened.structuredContent,before,'read-only calls changed live state');
 const report={date:new Date().toISOString(),scope:'installed MCP protocol and live read-only service; no native desktop card',
  upstream_revision:lock.revision,plugin_version:JSON.parse(await readFile(join(installed,'.codex-plugin/plugin.json'),'utf8')).version,
  installed_bundle_matches_locked_build:true,bundle_sha256:hashes,tools:names,
  cybertrack_data_directory_verified:true,cli_thread_target:null,service_revision:before.model.revision,
  part_count:before.model.parts.length,comment_count:before.comments.length,
  write_tools_called:0,native_message_delivery:'not_run',freecad_native_tool_edit:'not_run',same_card_update:'not_run'};
 const output=join(root,'output/solidcue/plugin-check-'+Date.now()+'.json');
 await mkdir(join(root,'output/solidcue'),{recursive:true});
 await writeFile(output,JSON.stringify(report,null,2)+'\n',{flag:'wx'});
 console.log(JSON.stringify({report:output,...report},null,2));
}finally{await client.close();}
