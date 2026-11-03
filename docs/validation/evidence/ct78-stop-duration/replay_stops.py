import gzip,json,sys
from pathlib import Path
sys.path.insert(0,'scripts')
from capture_lingxi import firmware_replay
root=Path('docs/validation/evidence/ct78-stop-duration')
exe=Path('build/ct78-full-host/firmware_host')
checks=[]
for path in sorted(root.glob('*.json.gz')):
 trace=json.loads(gzip.decompress(path.read_bytes()))
 for row in trace['results']:
  calls=row['host_calls']; wire_index=0
  for i,call in enumerate(calls):
   if 'name' not in call:continue
   wire=row['host_rpc_replies'][wire_index];wire_index+=1
   if call['name']!='self.tank.stop':continue
   receipt=json.loads(wire['result']['content'][0]['text'])
   before=firmware_replay(exe,row['initial_profile'],[*calls[:i],dict(inspect_ms=call['elapsed_ms'])],await_stt=True)[-1]
   later=firmware_replay(exe,row['initial_profile'],[*calls[:i+1],dict(inspect_ms=call['elapsed_ms']+60000)],await_stt=True)[-1]
   ok=receipt['result']=='ok' and receipt['operation']=='stop' and not any(receipt['logical_outputs'].values()) and not receipt['sequence_active']
   no_resume=not any(later['logical_outputs'].values()) and not later['sequence_active'] and later['starts_this_boot']==receipt['starts_this_boot']
   checks.append(dict(capture=path.name,id=row['id'],host_call_index=i,active_before=any(before['logical_outputs'].values()) or before['sequence_active'],receipt_stops_all=ok,no_resume_without_new_input_60s=no_resume,starts_at_receipt=receipt['starts_this_boot']))
assert all(r['receipt_stops_all'] and r['no_resume_without_new_input_60s'] for r in checks)
(root/'stop-control-review.json').write_text(json.dumps(dict(scope='Offline replay of each actual captured stop, then virtual 60 seconds without later input; no physical evidence; missing or unwanted model calls scored separately',stops=len(checks),active_before=sum(r['active_before'] for r in checks),passed=True,results=checks),ensure_ascii=False,indent=2)+'\n')
print('Stop control receipt/no-resume checks:',len(checks),'passed')
