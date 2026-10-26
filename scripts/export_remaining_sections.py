"""Export native section contours for path checks; run in FreeCAD's runtime."""
import sys,json
from pathlib import Path
import FreeCAD as A,Part
from check_head_print_paths import layers
O=Path(__file__).resolve().parents[1]/'hardware/model/remaining-print'
def main():
 paths=layers(O/'slicing/combined-classic/plate_1.gcode');hlist=list(paths)
 layout=json.loads((O/'slicing/combined-classic/layout.json').read_text());targets={'PP03-base':[1.6,18.2,22.5,40.5,78.5,86.5],'LC04-flipped':[2.5,9,12,15,17,24,27],'PP01-base':[1.5,3.5,5,8,16,21],'PP02-base':[1.5,4.5,8,24,37,42]};rows=[]
 for item in layout:
  name=item['stem'];bounds=item['bounds'];hlist=[h for h,segs in paths.items() if any(not f.startswith('Support') and f!='Brim' and bounds[0]<=a[0]<=bounds[2] and bounds[1]<=a[1]<=bounds[3] for a,b,w,f in segs)];s=Part.Shape();s.read(str(O/(name+'.brep')));b=s.optimalBoundingBox(False);s.translate(A.Vector(-(b.XMin+b.XMax)/2,-(b.YMin+b.YMax)/2,-b.ZMin));x,y=item['position']
  for target in targets[name]:
   height=min(hlist,key=lambda h:abs(h-target));z=height-.14
   wires=s.slice(A.Vector(0,0,1),z)
   contours=[[[p.x+x,p.y+y] for p in w.discretize(Deflection=.01)] for w in wires]
   rows.append({'name':name,'height':height,'cad_z':z,'contours':contours})
   print(name,height,len(wires),flush=True)
 (O/'section-contours.json').write_text(json.dumps(rows)+'\n')
if __name__=='__main__':main()
