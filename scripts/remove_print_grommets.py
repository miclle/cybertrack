"""Remove both cable grommets as requested; preserve all existing five-plate geometry."""
import json,hashlib,shutil
from pathlib import Path
import FreeCAD as A,Part
from update_pp02 import shape_rows,signature,same
ROOT=Path(__file__).resolve().parents[1];MODEL=ROOT/'hardware/model';OUT=MODEL/'completion-print';NAMES=['BaseCableGrommet','HeadCableGrommet']
def main():
 report={'removed':NAMES,'reason':'2026-10-26 user explicitly requested no cable grommets','documents':{}}
 for label,path in [('delivery',MODEL/'CyberTrack.FCStd'),('source',MODEL/'source/CyberTrack-design.FCStd')]:
  d=A.openDocument(str(path));before=shape_rows(d)
  for n in NAMES:
   if d.getObject(n):d.removeObject(n)
  d.recompute();assert all(same(v,signature(d.getObject(n).Shape)) for n,v in before.items() if n not in NAMES)
  d.save();expected=shape_rows(d);A.closeDocument(d.Name);d=A.openDocument(str(path));actual=shape_rows(d);assert set(actual)==set(expected) and all(same(v,actual[n]) for n,v in expected.items())
  report['documents'][label]={'other_objects_preserved':len(actual),'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
  if label=='delivery':Part.export([o for o in d.Objects if hasattr(o,'Shape') and not o.isDerivedFrom('App::DocumentObjectGroup') and getattr(o,'Category','') not in ('clearance','envelope')],str(MODEL/'CyberTrack.step'))
 archive=OUT/'superseded-grommet-study';archive.mkdir(exist_ok=True)
 for n in NAMES:
  for ext in ['stl','step','brep']:
   p=OUT/(n+'.'+ext)
   if p.exists():shutil.move(p,archive/p.name)
 if (OUT/'grommet-audit.json').exists():shutil.move(OUT/'grommet-audit.json',archive/'grommet-audit.json')
 (OUT/'grommet-removal.json').write_text(json.dumps(report,indent=2)+'\n');print('REMOVED GROMMETS',json.dumps(report),flush=True)
