"""Read saved CAD without modifying it; export hidden-line projections for the PDF.
Run with FreeCAD's bundled Python. Coordinates in the JSON are millimetres.
"""
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import FreeCAD as App
import Part
import TechDraw

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'tmp/pdfs'
OUT.mkdir(parents=True, exist_ok=True)
source = ROOT / 'hardware/model/CyberTrack.FCStd'
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
source_hash = sha(source)
doc = App.openDocument(str(source))
objects = [o for o in doc.Objects if hasattr(o, 'Category')]
visible = [o for o in objects if o.Category not in ('envelope','clearance')]
by_name = {o.Name: o for o in objects}
V = App.Vector
# Columns of each matrix define an explicit world-to-page mapping. Front page
# horizontal is +X; side is +Y; top has rear (+Y) at the top of the sheet.
matrices = {
    'front': ((1,0,0),(0,0,1),(0,-1,0)),
    'rear': ((-1,0,0),(0,0,1),(0,1,0)),
    'side': ((0,1,0),(0,0,1),(1,0,0)),
    'right': ((0,-1,0),(0,0,1),(-1,0,0)),
    'top': ((1,0,0),(0,1,0),(0,0,1)),
    'bottom': ((-1,0,0),(0,1,0),(0,0,-1)),
}
def project(key, names, view, clip=None):
    cache = OUT / f'{key}.json'
    if cache.exists():
        previous = json.loads(cache.read_text())
        if (previous.get('source_sha256') == source_hash and
                previous.get('projection_revision') == 3 and
                previous.get('view') == view and previous.get('names') == names and previous.get('clip') == clip):
            print(key, 'cached', flush=True)
            return
    matrix = App.Matrix()
    for i,row in enumerate(matrices[view]):
        for j,value in enumerate(row): setattr(matrix, f'A{i+1}{j+1}', value)
    compound = Part.makeCompound([by_name[n].Shape for n in names])
    if clip:
        x0,y0,z0,x1,y1,z1=clip
        compound=compound.common(Part.makeBox(x1-x0,y1-y0,z1-z0,V(x0,y0,z0)))
    # All view matrices are rigid rotations. Preserve analytic pipe bends;
    # transformGeometry unnecessarily converts tori to B-splines and may fail.
    transformed = compound.copy()
    transformed.transformShape(matrix)
    # project() omits outline edges of smooth surfaces in this FreeCAD build.
    # projectToSVG() includes the visible silhouettes as well as visible edges.
    svg = TechDraw.projectToSVG(transformed, V(0,0,1), 'Show', 0.08)
    (OUT/f'{key}.svg').write_text(svg)
    paths=[]
    root = ET.fromstring('<svg>'+svg+'</svg>')
    for element in root.iter():
        if element.tag in ('circle','ellipse'):
            cx=float(element.get('cx'));cy=float(element.get('cy'))
            rx=float(element.get('rx',element.get('r')))
            ry=float(element.get('ry',element.get('r')))
            n=max(24, math.ceil(math.pi/math.acos(max(-1,1-0.08/max(rx,ry)))))
            paths.append([[cx+rx*math.cos(2*math.pi*i/n),cy+ry*math.sin(2*math.pi*i/n)] for i in range(n+1)])
        elif element.tag=='path':
            tokens=re.findall(r'[A-Za-z]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?',element.get('d'))
            points=[];i=0
            def bezier(control):
                a,b=control[0],control[-1]
                vx,vy=b[0]-a[0],b[1]-a[1];den=vx*vx+vy*vy
                def distance(p):
                    t=max(0,min(1,((p[0]-a[0])*vx+(p[1]-a[1])*vy)/den)) if den else 0
                    return math.hypot(p[0]-a[0]-t*vx,p[1]-a[1]-t*vy)
                if max(map(distance,control))<=0.04:
                    points.append(b);return
                levels=[control]
                while len(levels[-1])>1:
                    last=levels[-1]
                    levels.append([[(x[0]+y[0])/2,(x[1]+y[1])/2] for x,y in zip(last,last[1:])])
                bezier([level[0] for level in levels])
                bezier([level[-1] for level in reversed(levels)])
            while i<len(tokens):
                command=tokens[i];i+=1
                if command in ('M','L'):
                    points.append([float(tokens[i]),float(tokens[i+1])]);i+=2
                elif command in ('Q','C'):
                    count=2 if command=='Q' else 3
                    control=[points[-1]]+[[float(tokens[i+2*j]),float(tokens[i+2*j+1])] for j in range(count)]
                    i+=2*count;bezier(control)
                elif command == 'A':
                    # SVG endpoint-form elliptical arc; sample to the same
                    # 0.08 mm chord tolerance as native circles and ellipses.
                    rx,ry,rotation,large,sweep,x2,y2=map(float,tokens[i:i+7]);i+=7
                    x1,y1=points[-1];rx,ry=abs(rx),abs(ry)
                    if not rx or not ry:
                        points.append([x2,y2]);continue
                    if math.hypot(x2-x1,y2-y1)<1e-12:continue
                    phi=math.radians(rotation);co,si=math.cos(phi),math.sin(phi)
                    dx,dy=(x1-x2)/2,(y1-y2)/2
                    xp,yp=co*dx+si*dy,-si*dx+co*dy
                    scale=max(1,math.sqrt((xp/rx)**2+(yp/ry)**2))
                    rx*=scale;ry*=scale
                    numerator=max(0,rx*rx*ry*ry-rx*rx*yp*yp-ry*ry*xp*xp)
                    denominator=rx*rx*yp*yp+ry*ry*xp*xp
                    factor=(-1 if bool(large)==bool(sweep) else 1)*math.sqrt(numerator/denominator)
                    cxp,cyp=factor*rx*yp/ry,-factor*ry*xp/rx
                    cx,cy=co*cxp-si*cyp+(x1+x2)/2,si*cxp+co*cyp+(y1+y2)/2
                    start=math.atan2((yp-cyp)/ry,(xp-cxp)/rx)
                    finish=math.atan2((-yp-cyp)/ry,(-xp-cxp)/rx)
                    angle=(finish-start)%(2*math.pi)
                    if not sweep:angle-=2*math.pi
                    step=2*math.acos(max(-1,1-0.08/max(rx,ry)))
                    count=max(1,math.ceil(abs(angle)/step))
                    for j in range(1,count+1):
                        t=start+angle*j/count;u,v=rx*math.cos(t),ry*math.sin(t)
                        points.append([cx+co*u-si*v,cy+si*u+co*v])
                    points[-1]=[x2,y2]
                elif command in ('Z','z'):points.append(points[0])
                else:raise ValueError(f'Unsupported SVG path command {command}')
            paths.append(points)
        elif element.tag not in ('svg','g'):
            raise ValueError(f'Unsupported SVG element {element.tag}')
    b=transformed.optimalBoundingBox(False)
    result={'source_sha256':source_hash,'projection_revision':3,'view':view,'names':names,'clip':clip,'bounds':[b.XMin,b.YMin,b.XMax,b.YMax], 'paths':paths}
    (OUT/f'{key}.json').write_text(json.dumps(result))
    print(key, len(paths), flush=True)

bounds={}
for o in objects:
    b=o.Shape.optimalBoundingBox(False)
    bounds[o.Name]={'label':o.Label,'bbox':[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]}
(OUT/'dimensions.json').write_text(json.dumps({'source_sha256':source_hash,'objects':bounds},ensure_ascii=False,indent=2))
for view in ('front','rear','side','right','top','bottom'):
    project(view, [o.Name for o in visible], view)
for key,names,view in [
    ('top_feed_top',['WaterPod','BubblePod','WaterServiceLid','BubbleServiceLid','WaterCapGrip','BubbleCapGrip','WaterHoseRoute','BubbleGunHoseRoute'],'top'),
    ('top_feed_side',['WaterPod','BubblePod','WaterServiceLid','BubbleServiceLid','WaterCapGrip','BubbleCapGrip','WaterHoseRoute','BubbleGunHoseRoute'],'side'),
    ('rear_armor_rear',['RearBaseArmor'],'rear'),
    ('rear_armor_side',['RearBaseArmor'],'side'),
    ('ultrasonic_front',['UltrasonicRingL','UltrasonicFaceL','UltrasonicRingR','UltrasonicFaceR','SensorStatusStrip'],'front'),
    ('ultrasonic_side',['SensorMask','UltrasonicRingL','UltrasonicFaceL','UltrasonicRingR','UltrasonicFaceR'],'side'),
    ('controller_top',['ESP32Board','ControllerCarrier','ControllerSocketFront','ControllerSocketRear','ControllerRetainer'],'top'),
    ('controller_front',['ESP32Board','ControllerCarrier','ControllerSocketFront','ControllerSocketRear','ControllerRetainer'],'front'),
    ('crown_effect_plan',['CrownFinL','CrownEffectInsetL','CrownEffectMarkLFront','CrownEffectMarkLRear'],'top'),
    ('arc_plan',['HeadShell','ElectronicsTray','Electronics','AudioModule','ArcModuleL','ArcModuleR','ESP32Board'],'top'),
    ('battery',['BatteryHatch','PowerBank','BatteryPullStrap'],'bottom'),
    ('tray',['ElectronicsTray'],'top'),
    ('crown',[o.Name for o in objects if getattr(o,'ServiceGroup','')=='crown'],'top'),
    ('fill_lid',['WaterServiceLid','WaterCapGrip'],'side'),
    ('fill_plug',['WaterFillPlug'],'side'),
    ('fill_seal',['WaterFillSeal'],'side'),
    ('fill_cap',['WaterPodCap'],'side'),
    ('fill_cap_top',['WaterPodCap'],'top'),
    ('fill',['WaterPodCap','WaterFillPlug','WaterFillSeal','WaterServiceLid','WaterCapGrip'],'side'),
    ('power_side',['PowerBank','BatteryHatch','BatteryPullStrap','BottomServiceCover'],'side'),
]:
    project(key,names,view)
project('drive_face',['LowerTub'],'side',clip=[73.3,-36,28,87.01,36,73])
project('drive_bottom',['LowerTub','BottomServiceCover']+[o.Name for o in objects if o.Name.startswith('BottomCoverScrew')],'bottom')
project('drive_cover',['BottomServiceCover'],'bottom')

assert source_hash==sha(source), 'Source CAD changed during readback'
App.closeDocument(doc.Name)
