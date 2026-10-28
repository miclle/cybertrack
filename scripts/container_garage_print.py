"""Eleven-piece FDM garage candidate. Use FreeCAD's GUI Python.

No source assembly is modified. Printed joints are candidate clearances and
standard fasteners are nominal envelopes, not released supplier geometry.
"""
import hashlib
import json
import math
from pathlib import Path

import FreeCAD as App
import Part
import MeshPart
import Mesh

import container_garage as base

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'hardware/model/container-garage/printed'
TARGET=OUT/'CyberTrack-garage-print-candidate.FCStd'
V=App.Vector
box=base.box
prism=base.prism
P={'printer':'P2SC (user supplied)','build_volume_mm':[256,256,256],
   'wall_mm':2.4,'roof_skin_mm':1.8,'body_height_mm':248,
   'floor_depth_mm':12,'door_length_mm':245,'door_root_mm':8,'door_tip_mm':2,
   'joint_clearance_mm':0.25,'brim_mm':2,'seam_y_mm':141,
   'robot_mass_kg':None,'manufacturing_released':False}


def dump(name,data):
    (OUT/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')


def fuse(shapes):
    return shapes[0].multiFuse(shapes[1:]).removeSplitter() if len(shapes)>1 else shapes[0]


def cylinder(radius,length,origin,axis=(0,0,1)):
    return Part.makeCylinder(radius,length,V(*origin),V(*axis))


def hexagon(af,z0,z1,x,y):
    r=af/math.sqrt(3)
    pts=[V(x+r*math.cos(i*math.pi/3),y+r*math.sin(i*math.pi/3),z0) for i in range(6)]
    return Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(0,0,z1-z0))


def screw_hole(shape,x,y,z0,z1,countersink=True):
    shape=shape.cut(cylinder(1.7,z1-z0+2,(x,y,z0-1)))
    if countersink:
        shape=shape.cut(Part.makeCone(1.7,3.2,1.8,V(x,y,z1-1.8)))
    return shape


def raw_body():
    parts=[box(-140,1,0,140,290,12)]
    for sign in (-1,1):
        a,b=sorted((sign*133.6,sign*136))
        parts.append(box(a,0,12,b,290,248))
        for y in range(18,276,22):
            a,b=sorted((sign*136,sign*139.6))
            parts.append(box(a,y,12,b,y+2.4,248))
        a,b=sorted((sign*130,sign*140))
        parts.extend([box(a,-8,0,b,10,248),box(a,280,0,b,290,248)])
    parts.append(box(-140,280,12,140,282.4,248))
    for x in range(-120,121,22):parts.append(box(x,282.4,12,x+2.4,286,248))
    body=fuse(parts)
    # Two separate hinge stations leave both track lanes clear.
    for cx in (-45,45):
        body=body.cut(box(cx-9,-5,2,cx+9,8,16))
        for x0,x1 in [(cx-15,cx-9),(cx+9,cx+15)]:
            ear=fuse([cylinder(3.6,x1-x0,(x0,0,12),(1,0,0)),box(x0,1,2,x1,8,12)])
            ear=ear.cut(cylinder(1.7,x1-x0+2,(x0-1,0,12),(1,0,0)))
            body=body.fuse(ear)
    # Roof screws: top-open nut pockets; insert nuts before fitting roof.
    for x in (-135,135):
        for y in (5,285):
            body=screw_hole(body,x,y,240,248,False)
            body=body.cut(hexagon(5.8,241,243.7,x,y))
            # Side-loading slot accessible from inside the open enclosure.
            a,b=(125,135) if x>0 else (-135,-125)
            body=body.cut(box(a,y-3,241,b,y+3,243.7))
    return body.removeSplitter()


def raw_roof():
    parts=[box(-140,-8,268.2,140,290,270),box(-140,-3,258,140,4,270),
           box(-140,280,248,140,290,270)]
    for a,b in [(-140,-130),(130,140)]:parts.append(box(a,-8,248,b,290,270))
    for x in (-70,0,70):parts.append(box(x-2,0,262,x+2,280,268.2))
    for y in (70,141,210):parts.append(box(-130,y-2,262,130,y+2,268.2))
    # Local pads carry full-depth locating fingers; avoid a thick solid roof.
    for x,y in [(6,70),(6,215),(-70,147),(70,147)]:
        parts.append(box(x-12,y-10,262,x+12,y+10,270))
    roof=fuse(parts)
    for x in (-135,135):
        for y in (5,285):
            roof=screw_hole(roof,x,y,248,270,False)
            roof=roof.cut(cylinder(3.3,18,(x,y,253)))
    # Cam axis sits in the thicker front header, not in the thin roof skin.
    roof=roof.cut(cylinder(1.7,10,(0,-4,264),(0,1,0)))
    # Clear the rotating cam from the roof's projecting front drip lip.
    # Leave 0.2 mm running clearance; only the header's outermost top edge is relieved.
    roof=roof.cut(box(-16,-8.1,268.1,16,-2.8,270.1))
    return roof.removeSplitter()


def quadrants(raw,kind):
    rows=[]
    for side in (-1,1):
        for rear in (False,True):
            xmin,xmax=(-140,0) if side<0 else (0,140)
            ymin,ymax=(141,290) if rear else (-8,141)
            z0,z1=(0,248) if kind=='body' else (248,270)
            shape=raw.common(box(xmin,ymin,z0,xmax,ymax,z1))
            low,mid,high=(0,6,12) if kind=='body' else (262,270,270)
            cy=215 if rear else 70
            # Lap tongues are local, backed by the deck or roof pads.
            if side<0:
                shape=shape.fuse(box(-1,cy-10,low,12,cy+10,mid))
            else:
                shape=shape.cut(box(-.1,cy-10.25,low-.1,12.25,cy+10.25,mid+.25))
            cx=70*side
            if not rear:
                shape=shape.fuse(box(cx-10,140,low,cx+10,153,mid))
            else:
                shape=shape.cut(box(cx-10.25,140.9,low-.1,cx+10.25,153.25,mid+.25))
            if kind=='body':
                # Full-height wall half-laps seal and align the vertical seams.
                if not rear:
                    a,b=sorted((side*134.8,side*136))
                    shape=shape.fuse(prism([(140,20),(141,20),(147,26),(147,240),(140,240)],a,b))
                else:
                    a,b=sorted((side*134.55,side*136.25))
                    shape=shape.cut(box(a,140.9,19.75,b,147.25,240.25))
                if rear and side<0:
                    pts=[V(-1,281.2,20),V(0,281.2,20),V(6,281.2,26),V(6,281.2,240),V(-1,281.2,240)]
                    tongue=Part.Face(Part.makePolygon(pts+[pts[0]])).extrude(V(0,1.2,0))
                    shape=shape.fuse(tongue)
                if rear and side>0:shape=shape.cut(box(-.1,280.95,19.75,6.25,282.65,240.25))
            if kind=='body':
                for x,y in [(6,cy),(cx,147)]:
                    shape=screw_hole(shape,x,y,low,high)
                    shape=shape.cut(hexagon(5.8,low,low+2.7,x,y))
            shape=shape.removeSplitter()
            stem=f'{"B" if kind=="body" else "R"}{len(rows)+1:02d}'
            rows.append((stem,shape,kind,side,rear))
    return rows


def door_parts():
    h,length,t0,t1=12.,P['door_length_mm'],P['door_root_mm'],P['door_tip_mm']
    wedge=prism([(0,h),(0,h+length),(-t1,h+length),(-t0,h)],-129.5,129.5)
    # Integral moving barrels and a supportless outer-face gusset.
    for cx in (-45,45):
        boss=fuse([cylinder(3.4,16,(cx-8,0,h),(1,0,0)),
                   prism([(-8,h),(-3.4,h-3.4),(0,h)],cx-8,cx+8)])
        wedge=wedge.fuse(boss)
    wedge=wedge.cut(cylinder(1.7,140,(-70,0,h),(1,0,0)))
    # Local fixed-barrel clearances, including the assembly gap.
    for cx in (-45,45):
        for x0,x1 in [(cx-15.25,cx-8.75),(cx+8.75,cx+15.25)]:
            wedge=wedge.cut(cylinder(3.85,x1-x0,(x0,0,h),(1,0,0)))
    rows=[]
    for side in (-1,1):
        shape=wedge.common(box(-140 if side<0 else 0,-15,0,0 if side<0 else 140,10,270))
        # Full-length half-depth lap, with two root screws away from track lanes.
        lap=prism([(-t0/2,h),(-t1/2,h+length),(-t1,h+length),(-t0,h)],-1,8)
        if side<0:shape=shape.fuse(lap)
        else:
            clearance=prism([(-t0/2+.25,h-.1),(-t1/2+.25,h+length+.1),(-t1-.25,h+length+.1),(-t0-.25,h-.1)],-.1,8.25)
            shape=shape.cut(clearance)
        for u in (18,58):
            shape=shape.cut(cylinder(1.7,16,(4,-12,h+u),(0,1,0)))
            # Hex nut pocket open from exterior, recessed below the tapered face.
            t=t0+(t1-t0)*u/length
            nut=hexagon(5.8,0,2.7,0,0)
            nut.Placement=App.Placement(V(4,-t-.15,h+u),App.Rotation(V(1,0,0),-90))
            shape=shape.cut(nut)
        rows.append((f'D{1 if side<0 else 2:02d}',shape.removeSplitter(),'door',side,False))
    return rows


def cam_shape():
    # Closed pose: 7 mm overlap over the door top, ~0.8 mm face clearance.
    shape=box(-5,-5.4,250,5,-3,268)
    shape=shape.cut(cylinder(1.7,4,(0,-6,264),(0,1,0)))
    return shape


def add(doc,group,stem,shape,kind):
    o=doc.addObject('Part::Feature',stem);o.Shape=shape;group.addObject(o)
    o.addProperty('App::PropertyString','Category');o.Category=kind
    o.addProperty('App::PropertyString','PartID');o.PartID=stem
    o.ViewObject.ShapeColor=(.98,.36,.06) if kind=='cam' else (.24,.28,.30)
    return o


def printable(shape,kind):
    s=shape.copy()
    if kind=='roof':s.rotate(V(),V(1,0,0),180)
    elif kind=='door':
        # Rotate the inclined exterior plane onto the bed; inner deck faces up.
        angle=math.degrees(math.atan2(P['door_root_mm']-P['door_tip_mm'],P['door_length_mm']))
        s.rotate(V(),V(1,0,0),90+angle)
    elif kind=='cam':s.rotate(V(),V(1,0,0),-90)
    b=s.optimalBoundingBox(False,False)
    s.translate(V(-(b.XMin+b.XMax)/2,-(b.YMin+b.YMax)/2,-b.ZMin))
    return s


def build():
    import FreeCADGui as Gui
    global DOC,ROWS,SOURCE_HASHES
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'parts').mkdir(exist_ok=True)
    for doc in App.listDocuments().values():
        if doc.FileName and Path(doc.FileName).resolve()==TARGET.resolve():
            raise RuntimeError('Printed candidate already open; preserve it before rebuilding')
    baseline=ROOT/'hardware/model/container-garage/CyberTrack-container-garage.FCStd'
    SOURCE_HASHES={str(p.relative_to(ROOT)):base.sha(p) for p in (baseline,base.SOURCE)}
    source=next((d for d in App.listDocuments().values() if d.FileName and Path(d.FileName).resolve()==baseline.resolve()),None)
    owned=source is None
    if owned:source=App.openDocument(str(baseline))
    DOC=App.newDocument('CyberTrackGaragePrint');DOC.Label='CyberTrack · 11件打印车库候选'
    for name,label in [('GarageFixed','01 角舱与顶盖'),('Door','02 双片下翻门'),('Lock','03 旋转门闩'),('Robot','04 机器人快照')]:
        group=DOC.addObject('App::Part',name);group.Label=label
    rows=quadrants(raw_body(),'body')+quadrants(raw_roof(),'roof')+door_parts()+[('L01',cam_shape(),'cam',0,False)]
    ROWS=[]
    for stem,shape,kind,side,rear in rows:
        assert shape.isValid() and len(shape.Solids)==1,(stem,shape.isValid(),len(shape.Solids))
        group=DOC.Door if kind=='door' else DOC.Lock if kind=='cam' else DOC.GarageFixed
        o=add(DOC,group,stem,shape,kind)
        o.Label=f'{stem} · '+{'body':'底板侧壁一体角舱','roof':'可拆顶盖分片','door':'坡道门分片','cam':'旋转门闩'}[kind]
        s=printable(shape,kind);b=s.optimalBoundingBox(False,False)
        size=[b.XLength,b.YLength,b.ZLength]
        assert max(size[:2])+2*P['brim_mm']<=256.0001 and size[2]<=256,(stem,size)
        mesh=MeshPart.meshFromShape(Shape=s,LinearDeflection=.06,AngularDeflection=.12,Relative=False)
        path=OUT/'parts'/(stem+'.stl');mesh.write(str(path));back=Mesh.Mesh(str(path))
        assert back.isSolid() and not back.hasNonManifolds(),stem
        ROWS.append({'id':stem,'kind':kind,'side':side,'rear':rear,'print_size_xyz_mm':size,
                     'bbox_in_assembly_mm':base.exact_bounds(shape),'volume_mm3':shape.Volume,
                     'solids':len(shape.Solids),'stl_closed':True,'stl_sha256':base.sha(path),
                     'material':'PLA Basic candidate','manufacturing_released':False})
    for original in source.Robot.Group:
        if not hasattr(original,'Shape'):continue
        o=add(DOC,DOC.Robot,original.Name,original.Shape.copy(),'robot')
        o.addProperty('App::PropertyString','SourceObject');o.SourceObject=original.SourceObject
        o.ViewObject.ShapeColor=original.ViewObject.ShapeColor
        o.ViewObject.Visibility=original.ViewObject.Visibility
    # Reuse the established motion-expression convention, with the new 2 mm toe.
    state=DOC.addObject('App::FeaturePython','Pose')
    for name,typ,value in [('DoorAngle','App::PropertyAngle',0),('RobotY','App::PropertyDistance',155.12319342526249),
                           ('RobotZ','App::PropertyDistance',12),('RobotPitch','App::PropertyAngle',0),('LockAngle','App::PropertyAngle',90)]:
        state.addProperty(typ,name,'Pose');setattr(state,name,value)
    DOC.Door.Placement=App.Placement(V(),App.Rotation(V(1,0,0),.001),V(0,0,12))
    DOC.Door.setExpression('Placement.Rotation.Angle','Pose.DoorAngle')
    DOC.Door.setExpression('Placement.Base.y','12 mm * sin(Pose.DoorAngle)')
    DOC.Door.setExpression('Placement.Base.z','12 mm * (1-cos(Pose.DoorAngle))')
    DOC.Robot.Placement=App.Placement(V(0,155.12319342526249,12),App.Rotation(V(1,0,0),.001))
    for prop,expr in [('Placement.Rotation.Angle','Pose.RobotPitch'),('Placement.Base.y','Pose.RobotY'),('Placement.Base.z','Pose.RobotZ')]:DOC.Robot.setExpression(prop,expr)
    DOC.Lock.Placement=App.Placement(V(),App.Rotation(V(0,1,0),.001),V(0,-3,264))
    DOC.Lock.setExpression('Placement.Rotation.Angle','Pose.LockAngle')
    DOC.Lock.setExpression('Placement.Base.x','-264 mm * sin(Pose.LockAngle)')
    DOC.Lock.setExpression('Placement.Base.z','264 mm * (1-cos(Pose.LockAngle))')
    DOC.recompute();App.setActiveDocument(DOC.Name)
    Gui.activeDocument().activeView().viewAxonometric();Gui.activeDocument().activeView().fitAll()
    DOC.saveAs(str(TARGET))
    if owned:App.closeDocument(source.Name)
    for p,digest in SOURCE_HASHES.items():assert base.sha(ROOT/p)==digest
    dump('parameters.json',P);dump('parts.json',ROWS)
    print(json.dumps({'parts':len(ROWS),'max_print_size':[max(r['print_size_xyz_mm'][i] for r in ROWS) for i in range(3)],'file':str(TARGET)}))


def prepare_validation():
    """Detached snapshots only; uses the existing spatial checker with revised inputs."""
    base.OUT=OUT;base.TARGET=TARGET
    base.P.update(inner_height=246,door_top_gap=1,door_tip_thickness=2)
    base.open_angle.cache_clear()
    base._TARGET_BOUNDS={};base._LAST_BROAD_PHASE=[None,None]
    base.DOC=DOC;base.FIXED=DOC.GarageFixed;base.DOOR=DOC.Door;base.ROBOT=DOC.Robot
    base.PARK_Y=155.12319342526249;base.SOURCE_HASH=base.sha(base.SOURCE)
    DOC.Pose.LockAngle=90;DOC.recompute()
    lock=DOC.L01.Shape.copy();lock.Placement=DOC.Lock.Placement.multiply(lock.Placement)
    base.DETACHED={'fixed':[(o.Name,o.Category,o.Shape.copy()) for o in DOC.GarageFixed.Group]+[('ReleasedCam','cam',lock)],
                   'door':[(o.Name,'door',o.Shape.copy()) for o in DOC.Door.Group],
                   'robot':[(o.SourceObject,'robot',o.Shape.copy()) for o in DOC.Robot.Group],
                   'source_hash':base.SOURCE_HASH,'park_y':base.PARK_Y}
    install_cavity_broad_phase()
    return base.open_angle()


def install_cavity_broad_phase():
    """Reject moving bounds fully inside an exactly checked empty body cavity."""
    cavity=box(-130,-1000,16,130,280,248)
    bodies=[s for _,c,s in base.DETACHED['fixed'] if c=='body']
    checks=[s.common(cavity).Volume for s in bodies]
    assert all(v<1e-7 for v in checks),checks
    body_ids={id(s) for s in bodies}
    original=getattr(base,'_GARAGE_ORIGINAL_OVERLAPS',base.overlaps)
    base._GARAGE_ORIGINAL_OVERLAPS=original
    def overlaps(a,b,eps=1e-7):
        if not original(a,b,eps):return False
        if id(b) in body_ids:
            lohi=base._LAST_BROAD_PHASE[1]
            if lohi[0]>-130 and lohi[3]<130 and lohi[1]>-1000 and lohi[4]<280 and lohi[2]>16 and lohi[5]<248:
                return False
        return True
    base.overlaps=overlaps
    dump('cavity-broad-phase.json',{'empty_cavity_xyz_mm':[-130,-1000,16,130,280,248],
        'body_intersection_volumes_mm3':checks,'proof':'Only fully contained moving bounding boxes are rejected; all other candidates retain exact solid intersection checks.'})


def detail_check():
    """Check nominal mating geometry and manual latch motion on copied solids."""
    fixed=[(o.Name,o.Shape.copy()) for o in DOC.GarageFixed.Group]
    doors=[(o.Name,o.Shape.copy()) for o in DOC.Door.Group]
    cam=DOC.L01.Shape.copy()
    hits=[]
    for i,(name,s) in enumerate(fixed+doors):
        for other,t in (fixed+doors)[i+1:]:
            if base.overlaps(s,t):
                volume=s.common(t).Volume
                if volume>.01:hits.append([name,other,volume])
    latch_hits=[]
    for angle in range(91):
        s=cam.copy();s.rotate(V(0,-3,264),V(0,1,0),angle)
        for name,t in fixed+doors:
            if base.overlaps(s,t):
                volume=s.common(t).Volume
                if volume>.01:latch_hits.append([angle,name,volume])
    locked=0
    for _,original in doors:
        s=original.copy();s.Placement=base.door_placement(.5).multiply(s.Placement)
        locked+=s.common(cam).Volume
    unchanged=[]
    for name,_,s in base.DETACHED['door']:
        now=DOC.getObject(name).Shape
        difference=now.cut(s).Volume+s.cut(now).Volume
        unchanged.append({'part':name,'symmetric_difference_mm3':difference})
    result={'mating_part_hits':hits,'latch_rotation_0_to_90_deg_hits':latch_hits,
            'locked_door_at_half_degree_overlap_mm3':locked,
            'door_snapshot_comparison':unchanged,
            'passed':not hits and not latch_hits and locked>.01 and all(r['symmetric_difference_mm3']<.01 for r in unchanged),
            'limits':'Nominal printed parts only. Fastener fit, latch retention force, friction and printed tolerances require physical trials.'}
    dump('detail-check.json',result)
    return result


def refresh_print_parts():
    """Refresh this task's open candidate after an explicitly scoped joint change."""
    global ROWS
    old={o.Name:o.Shape.copy() for o in DOC.GarageFixed.Group}
    rows=quadrants(raw_body(),'body')+quadrants(raw_roof(),'roof')+door_parts()+[('L01',cam_shape(),'cam',0,False)]
    ROWS=[];changes=[]
    for stem,shape,kind,side,rear in rows:
        assert shape.isValid() and len(shape.Solids)==1,stem
        if stem in old:
            added=shape.cut(old[stem]);removed=old[stem].cut(shape)
            changes.append({'id':stem,'added_volume_mm3':added.Volume,'removed_volume_mm3':removed.Volume,
                            'added_bbox_mm':base.exact_bounds(added) if added.Volume>1e-6 else None})
        DOC.getObject(stem).Shape=shape
        s=printable(shape,kind);b=s.optimalBoundingBox(False,False);size=[b.XLength,b.YLength,b.ZLength]
        assert max(size[:2])+2*P['brim_mm']<=256.0001 and size[2]<=256,stem
        path=OUT/'parts'/(stem+'.stl')
        MeshPart.meshFromShape(Shape=s,LinearDeflection=.06,AngularDeflection=.12,Relative=False).write(str(path))
        m=Mesh.Mesh(str(path));assert m.isSolid() and not m.hasNonManifolds(),stem
        ROWS.append({'id':stem,'kind':kind,'side':side,'rear':rear,'print_size_xyz_mm':size,
                     'bbox_in_assembly_mm':base.exact_bounds(shape),'volume_mm3':shape.Volume,'solids':1,
                     'stl_closed':True,'stl_sha256':base.sha(path),'material':'PLA Basic candidate','manufacturing_released':False})
    # Changing the ownership of a joint can add material to one part while removing
    # it from its mate. Validate the combined enclosure, not each part in isolation.
    before=fuse(list(old.values()));after=fuse([DOC.getObject(n).Shape for n in old])
    added=after.cut(before)
    corridor=box(-120,-600,0,120,280,258)
    proof=added.common(corridor).Volume
    assert proof<.01,proof
    dump('joint-refinement.json',{'changes':changes,'union_added_volume_mm3':added.Volume,
        'union_added_bbox_mm':base.exact_bounds(added) if added.Volume>1e-6 else None,
        'added_intersection_with_motion_corridor_mm3':proof,
        'motion_corridor_xyz_mm':[-120,-600,0,120,280,258],
        'door_unchanged':True,'proof':'Added fixed material is outside conservative robot corridor and above door sweep; unchanged door and reduced wall material preserve prior path checks.'})
    DOC.recompute();DOC.save();dump('parts.json',ROWS)
    return changes


def finish():
    """Render, save and reopen only the printed candidate created by this task."""
    import FreeCADGui as Gui
    from PySide import QtGui
    global DOC
    assert base.RESULT['passed']
    detail=detail_check();assert detail['passed']
    report=base.RESULT
    report['revision']='printed-11-parts-r1'
    report['parameters']['revision']='printed-11-parts-r1'
    report['printed_parameters']=P
    report['fixed_geometry_refinements']=[json.loads((OUT/n).read_text()) for n in ('joint-refinement.json','cam-clearance-fix.json')]
    report['detail_check']='detail-check.json'
    report['fasteners_in_motion_check']=False
    b=Part.makeCompound([s for _,_,s in base.DETACHED['robot']]).optimalBoundingBox(False,False)
    report['source_bbox_mm']=[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]
    report['closed_clearances_mm']={'left':130+b.XMin,'right':130-b.XMax,
        'front':b.YMin+base.PARK_Y,'rear':280-b.YMax-base.PARK_Y,'front_header_top':246-b.ZMax}
    report['source_bbox_method']='optimalBoundingBox(False,False)'
    report['current_native_parts']={r['id']:r['stl_sha256'] for r in ROWS}
    for row in ROWS:
        path=OUT/'parts'/(row['id']+'.stl')
        mesh=Mesh.Mesh(str(path))
        assert mesh.isSolid() and not mesh.hasNonManifolds(),row['id']
        assert base.sha(path)==row['stl_sha256'],row['id']
    dump('spatial-validation.json',report)
    App.setActiveDocument(DOC.Name)
    view=Gui.activeDocument().activeView()
    view.stopAnimating();view.setAnimationEnabled(False);view.setCameraType('Orthographic')
    iso=App.Rotation(V(1,.55,0),V(0,0,1),V(.55,-1,.36),'ZXY')
    for state in ('closed','open','ramp','exit'):
        DOC.Pose.LockAngle=0 if state=='closed' else 90
        base.set_pose(state)
        view.setCameraOrientation(iso.Q);view.fitAll()
        for _ in range(5):QtGui.QApplication.processEvents()
        view.saveImage(str(OUT/(state+'.png')),1600,1200,'White')
    base.set_pose('open');DOC.Robot.Visibility=False
    placements={r['id']:DOC.getObject(r['id']).Placement.copy() for r in ROWS}
    for row in ROWS:
        obj=DOC.getObject(row['id'])
        if row['kind'] in ('body','roof'):
            obj.Placement.Base=V(row['side']*35,35 if row['rear'] else -35,90 if row['kind']=='roof' else 0)
        elif row['kind']=='door':obj.Placement.Base=V(row['side']*25,0,0)
    DOC.recompute();view.fitAll()
    for _ in range(5):QtGui.QApplication.processEvents()
    view.saveImage(str(OUT/'exploded.png'),1600,1200,'White')
    for name,placement in placements.items():DOC.getObject(name).Placement=placement
    DOC.Robot.Visibility=True
    base.set_pose('open');DOC.Pose.LockAngle=90;DOC.recompute();view.fitAll();DOC.save()
    expected={o.Name:{'volume':o.Shape.Volume,'bbox':base.exact_bounds(o.Shape),'valid':o.Shape.isValid(),'visible':o.Visibility}
        for o in DOC.Objects if o.TypeId=='Part::Feature' and hasattr(o,'Shape')}
    App.closeDocument(DOC.Name);DOC=App.openDocument(str(TARGET))
    for name,row in expected.items():
        o=DOC.getObject(name);s=o.Shape
        assert s.isValid() and abs(s.Volume-row['volume'])<.001,name
        assert max(abs(a-b) for a,b in zip(base.exact_bounds(s),row['bbox']))<.00001,name
        assert o.Visibility==row['visible'],name
    for path,digest in SOURCE_HASHES.items():assert base.sha(ROOT/path)==digest,path
    base.DOC=DOC;base.FIXED=DOC.GarageFixed;base.DOOR=DOC.Door;base.ROBOT=DOC.Robot
    dump('saved-readback.json',{'native_file':TARGET.name,'native_sha256':base.sha(TARGET),
        'objects_verified':len(expected),'geometry_valid':True,'gui_reopened':True,'saved_pose':'open-unlocked',
        'source_hashes_unchanged':SOURCE_HASHES,'manufacturing_released':False})
    print('SAVED AND REOPENED',len(expected))
