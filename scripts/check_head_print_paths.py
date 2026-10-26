"""Check sampled PP07 connection/post sections in emitted G-code, not physical strength."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import zipfile


def layers(project, include_support=False):
    if Path(project).suffix=='.gcode':
        text=Path(project).read_text()
    else:
        with zipfile.ZipFile(project) as archive:
            text=archive.read('Metadata/plate_1.gcode').decode()
    result={}; x=y=0.; height=None; width=.42; feature=''; relative=False
    for line in text.splitlines():
        if line.startswith('; Z_HEIGHT:'):height=float(line.split(':')[1]);result.setdefault(height,[])
        if line.startswith('; FEATURE:'):feature=line.split(':',1)[1].strip()
        if line.startswith('; LINE_WIDTH:'):width=float(line.split(':')[1])
        code=line.split(';')[0].strip()
        if code=='M83':relative=True
        if code=='M82':relative=False
        command=code.split(' ',1)[0]
        if command not in ('G0','G1','G2','G3'):continue
        values={k:float(v) for k,v in re.findall(r'([XYEIJ])(-?\d*\.?\d+)',code)}
        nx=values.get('X',x);ny=values.get('Y',y)
        if height is not None and values.get('E',0)>0 and feature not in (('Custom',) if include_support else ('Custom','Support','Support interface','Brim')):
            assert relative, 'Parser expects relative extrusion'
            points=[(x,y),(nx,ny)]
            if command in ('G2','G3') and ('I' in values or 'J' in values):
                cx=x+values.get('I',0);cy=y+values.get('J',0)
                r=math.hypot(x-cx,y-cy);a=math.atan2(y-cy,x-cx);end=math.atan2(ny-cy,nx-cx)
                span=(end-a)%(2*math.pi) if command=='G3' else -((a-end)%(2*math.pi))
                if abs(span)<1e-8:span=2*math.pi if command=='G3' else -2*math.pi
                count=max(1,math.ceil(abs(span)*r/.12))
                points=[(cx+r*math.cos(a+span*i/count),cy+r*math.sin(a+span*i/count)) for i in range(count+1)]
            result[height].extend((p,q,width,feature) for p,q in zip(points,points[1:]) if p!=q)
        x,y=nx,ny
    return result


def distance(px,py,a,b):
    dx=b[0]-a[0];dy=b[1]-a[1]
    t=max(0,min(1,((px-a[0])*dx+(py-a[1])*dy)/(dx*dx+dy*dy)))
    return math.hypot(px-a[0]-t*dx,py-a[1]-t*dy)


def check(project):
    paths=layers(project);targets=[]
    for x in (-64,64):
        for y in (-52,7):targets.append((f'crown_{x}_{y}',x,y,211,7,7,'annulus'))
    for x in (-57,57):
        for y in (-40,-5):targets.append((f'tray_{x}_{y}',x,y,168,7,7,'annulus'))
    for x in (-19,17):targets.append((f'jaw_{x}',x,-80.25,170.5,6,8.5,'box'))
    for sign in (-1,1):
        targets.extend([(f'sensor_{sign}',sign*62,-80.5,187,6,3,'box'),
                        (f'cheek_{sign}',sign*72,-83.5,175,6,3,'box'),
                        (f'hub_{sign}',sign*87.25,-9,188,3.5,6,'box')])
        for z in (174,202):targets.append((f'ear_{sign}_{z}',sign*85.75,-9,z,2.5,4,'box'))
    rows=[]
    for name,x,y,z,w,d,kind in targets:
        x+=128;y+=154.75;z-=161
        height=min(paths,key=lambda h:abs(h-z))
        nearby=[s for s in paths[height] if max(s[0][0],s[1][0])+s[2]/2>=x-w/2 and
            min(s[0][0],s[1][0])-s[2]/2<=x+w/2 and max(s[0][1],s[1][1])+s[2]/2>=y-d/2 and
            min(s[0][1],s[1][1])-s[2]/2<=y+d/2]
        total=covered=0
        for i in range(math.ceil(w/.15)):
            for j in range(math.ceil(d/.15)):
                px=x-w/2+(i+.5)*.15;py=y-d/2+(j+.5)*.15
                if kind=='annulus' and not 1.05<math.hypot(px-x,py-y)<3.5:continue
                total+=1
                covered+=any(distance(px,py,a,b)<=width/2+.02 for a,b,width,_ in nearby)
        fraction=covered/total
        rows.append(dict(name=name,sampled_z_mm=height,segments=len(nearby),
            approximate_material_coverage=fraction,passed=fraction>.5,
            features=sorted({s[3] for s in nearby})))
    return dict(project_sha256=hashlib.sha256(project.read_bytes()).hexdigest(),checks=rows,
        passed=all(row['passed'] for row in rows),minimum_coverage_screen=0.5,
        method='Sampled midpoint sections: 0.15 mm raster, circular G-code arcs subdivided at <=0.12 mm; extrusion width footprint with 0.02 mm tolerance; support excluded',
        limits='Presence/coverage screen only; not full-layer connectivity, extrusion simulation, strength or fit proof. Two perimeter seam bands are not included in these 20 sampled sections.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project',type=Path);parser.add_argument('output',type=Path)
    args=parser.parse_args();report=check(args.project)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({r['name']:round(r['approximate_material_coverage'],3) for r in report['checks']}))
    if not report['passed']:raise SystemExit('Sampled coverage screen failed; inspect saved report')
