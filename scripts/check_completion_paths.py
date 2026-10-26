"""Sample native material footprints against actual extrusion paths, including thin guides."""
import json,math,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
from check_head_print_paths import layers
from check_remaining_paths import coverage
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'hardware/model/completion-print'

def material_points(contours,step=.20):
 pts=[p for c in contours for p in c]
 if not pts:return []
 lo=[min(p[i] for p in pts)-.1 for i in [0,1]];hi=[max(p[i] for p in pts)+.1 for i in [0,1]];pix=.04;size=[math.ceil((hi[i]-lo[i])/pix)+1 for i in [0,1]];im=Image.new('1',size)
 for c in contours:
  wire=Image.new('1',size);ImageDraw.Draw(wire).polygon([((p[0]-lo[0])/pix,(p[1]-lo[1])/pix) for p in c],fill=1);im=ImageChops.logical_xor(im,wire)
 values=im.load();return [[lo[0]+(x+.5)*step,lo[1]+(y+.5)*step] for x in range(math.floor((hi[0]-lo[0])/step)) for y in range(math.floor((hi[1]-lo[1])/step)) if values[round((x+.5)*step/pix),round((y+.5)*step/pix)]]
def main():
 contours=json.loads((OUT/'section-contours.json').read_text());reports={}
 for name,rows in contours.items():
  gc=OUT/'slicing'/name/('plate_6.gcode' if name=='merged-validation' else 'plate_1.gcode');paths=layers(gc);out=[]
  for r in rows:
   points=material_points(r['contours']);fraction=coverage(points,paths[r['height']]);limit=.2 if r['part'].endswith('Pod') and 1<r['height']<4 else .55
   out.append({'part':r['part'],'height':r['height'],'target':r['target'],'sample_points':len(points),'coverage':fraction,'minimum':limit,'passed':bool(points) and fraction>=limit})
  reports[name]={'gcode_sha256':hashlib.sha256(gc.read_bytes()).hexdigest(),'sections':out}
 baseline=reports['reference-024']['sections']
 for name,report in reports.items():
  for row,ref in zip(report['sections'],baseline):
   row['baseline_coverage']=ref['coverage'];row['passed']=row['passed'] and row['coverage']>=ref['coverage']-.08
  report['passed']=all(x['passed'] for x in report['sections'])
  print(name,report['passed'],[(x['part'],x['height'],round(x['coverage'] or 0,3),round(x['baseline_coverage'] or 0,3)) for x in report['sections'] if not x['passed']])
 (OUT/'path-check.json').write_text(json.dumps({'method':'Native contours at actual layer midplanes; 0.04 mm contour raster / 0.2 mm material grid / extrusion width footprint; excludes support. Local thin-wall preservation, not strength acceptance.','candidates':reports},indent=2)+'\n')
if __name__=='__main__':main()
