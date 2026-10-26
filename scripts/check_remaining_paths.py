"""Compare native section samples against emitted extrusion footprints."""
import json,math,hashlib
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops
from check_head_print_paths import layers
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'hardware/model/remaining-print';STEP=.025

def coverage(points,segments):
 if not points:return None
 x0=min(p[0] for p in points)-1;y0=min(p[1] for p in points)-1;x1=max(p[0] for p in points)+1;y1=max(p[1] for p in points)+1
 im=Image.new('1',(math.ceil((x1-x0)/STEP)+1,math.ceil((y1-y0)/STEP)+1));draw=ImageDraw.Draw(im)
 def px(p):return ((p[0]-x0)/STEP,(p[1]-y0)/STEP)
 for a,b,width,feature in segments:
  if feature.startswith('Support') or feature=='Brim' or feature=='Custom':continue
  if max(a[0],b[0])+width<x0 or min(a[0],b[0])-width>x1 or max(a[1],b[1])+width<y0 or min(a[1],b[1])-width>y1:continue
  aa,bb=px(a),px(b);w=max(1,round((width+.04)/STEP));draw.line([aa,bb],fill=1,width=w)
  r=w/2
  for x,y in [aa,bb]:draw.ellipse((x-r,y-r,x+r,y+r),fill=1)
 pix=im.load();return sum(bool(pix[round(px(p)[0]),round(px(p)[1])]) for p in points)/len(points)

def sample_contours():
 rows=[]
 for row in json.loads((OUT/'section-contours.json').read_text()):
  points=[p for contour in row['contours'] for p in contour]
  if not points:continue
  x0=min(p[0] for p in points)-.1;y0=min(p[1] for p in points)-.1;x1=max(p[0] for p in points)+.1;y1=max(p[1] for p in points)+.1
  pixel=.05;size=(math.ceil((x1-x0)/pixel)+1,math.ceil((y1-y0)/pixel)+1);im=Image.new('1',size)
  for contour in row['contours']:
   wire=Image.new('1',size);ImageDraw.Draw(wire).polygon([((p[0]-x0)/pixel,(p[1]-y0)/pixel) for p in contour],fill=1);im=ImageChops.logical_xor(im,wire)
  def sample(bounds,step):
   a,b,c,d=bounds;output=[];pix=im.load()
   for i in range(math.ceil((c-a)/step)):
    for j in range(math.ceil((d-b)/step)):
     x=a+(i+.5)*step;y=b+(j+.5)*step;xx=round((x-x0)/pixel);yy=round((y-y0)/pixel)
     if 0<=xx<size[0] and 0<=yy<size[1] and pix[xx,yy]:output.append([x,y])
   return output
  rows.append(dict(name=row['name'],height=row['height'],points=sample((x0,y0,x1,y1),.4)))
  if row['name']=='LC04-flipped' and 8<row['height']<18:
   for sign in (-1,1):
    a,b=sorted((73+sign*40,73+sign*49));rows.append(dict(name='LC04-rib-'+str(sign),height=row['height'],points=sample((a,162.5,b,165.5),.2)))
 return rows

def main():
 samples=sample_contours();candidates=['combined-classic','combined-arachne','combined-wide','combined-wide-arachne','merged-validation'];reports={}
 for name in candidates:
  file=OUT/'slicing'/name/('plate_5.gcode' if name=='merged-validation' else 'plate_1.gcode');paths=layers(file);rows=[]
  for sample in samples:
   height=min(paths,key=lambda h:abs(h-sample['height']));fraction=coverage(sample['points'],paths[height]);rows.append({'part':sample['name'],'height':height,'points':len(sample['points']),'coverage':fraction})
  reports[name]={'gcode_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'sections':rows}
 baseline=reports['combined-classic']['sections']
 for name,report in reports.items():
  for row,ref in zip(report['sections'],baseline):
   row['baseline_coverage']=ref['coverage'];minimum=.85 if row['part'].startswith('LC04-rib') else .2 if row['part'] in ('PP01-base','PP02-base') and row['height']<2 else .55
   row['passed']=row['points']>0 and row['coverage']>=minimum and row['coverage']>=ref['coverage']-.05
  report['passed']=all(r['passed'] for r in report['sections'])
  print(name,report['passed'],[(r['part'],r['height'],round(r['coverage'] or 0,3),round(r['baseline_coverage'] or 0,3)) for r in report['sections'] if not r['passed']])
 output={'method':'Native section contours at sampled layer midplanes, curve deflection 0.01 mm, contour raster 0.05 mm; 0.4 mm grid, lid ribs 0.2 mm. G-code footprint raster 0.025 mm, width +0.04 mm tolerance, support excluded; no >5 percentage-point loss vs 3x0.5 classic reference.','limits':'Sampled path preservation only, not physical strength or whole-volume simulation.','candidates':reports}
 (OUT/'path-check.json').write_text(json.dumps(output,indent=2)+'\n')
if __name__=='__main__':main()
