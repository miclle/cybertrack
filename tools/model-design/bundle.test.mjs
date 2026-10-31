import {test} from 'node:test';
import assert from 'node:assert/strict';
import {copyFile,mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {Client} from '@modelcontextprotocol/sdk/client/index.js';
import {StdioClientTransport} from '@modelcontextprotocol/sdk/client/stdio.js';

// Protocol-only: no model tools, service writes, plugin installation or desktop acceptance.
test('newly built plugin exposes compatible tools and a self-contained model resource', {timeout:30000}, async()=>{
  // A space in the installation path must not be passed to Node as URL-encoded %20.
  const directory=await mkdtemp(join(tmpdir(),'solidcue bundle-'));
  const client=new Client({name:'solidcue-bundle-test',version:'1.0.0'});
  try {
    for(const filename of ['mcp-server.mjs','model.html'])
      await copyFile(new URL(`./plugin/dist/${filename}`,import.meta.url),join(directory,filename));
    const transport=new StdioClientTransport({command:process.execPath,
      args:[join(directory,'mcp-server.mjs')],cwd:directory});
    await client.connect(transport);
    const {tools}=await client.listTools();
    assert.deepEqual(tools.map(tool=>tool.name).sort(),[
      'acknowledge_comment','apply_center_hole','create_mounting_plate','create_spacer',
      'export_step','get_state','open_model','save_comment','save_step','sync_cad_snapshot',
      'undo_model','update_plate_hole_spacing','update_spacer_parameters',
    ]);
    const sync=tools.find(tool=>tool.name==='sync_cad_snapshot');
    assert.deepEqual(sync.inputSchema.required,['documentId','expectedRevision','snapshotId','mode']);
    assert.equal(sync.inputSchema.additionalProperties,false);
    const edit=tools.find(tool=>tool.name==='update_plate_hole_spacing');
    assert.deepEqual(edit.inputSchema.required,['documentId','expectedRevision','commentId','sha256','holeSpacingMm']);
    assert.equal(edit.inputSchema.additionalProperties,false);
    const resource=await client.readResource({uri:'ui://cad-comment/model.html'});
    const html=resource.contents[0].text;
    assert.match(html,/<script type="module">/);
    assert.match(html,/<style>/);
    assert.doesNotMatch(html,/<script[^>]+src=|<link[^>]+stylesheet|importmap/);
    assert.match(html,/ui\/message/);
    assert.match(html,/update_plate_hole_spacing/);
    assert.equal(html.includes('来自独立 SolidCue 页面的评论'),false);
    assert.deepEqual(resource.contents[0]._meta.ui.csp,{connectDomains:[],resourceDomains:[]});
  } finally {
    try {await client.close();}
    finally {await rm(directory,{recursive:true,force:true});}
  }
});
