"""Build a separate garage and immutable robot snapshot in GUI-enabled FreeCAD.

Run build(), prepare_validation(), validate(), and finish() in that order.
validate() only uses detached OCCT shapes and can run in the MCP background worker.
Dimensions are script parameters, not a fabrication release. No source is saved.
"""
import hashlib
from functools import lru_cache
import json
import math
from pathlib import Path

import FreeCAD as App
import Part
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'hardware/model/container-garage'
SOURCE = ROOT / 'hardware/model/CyberTrack.FCStd'
TARGET = OUT / 'CyberTrack-container-garage.FCStd'
V = App.Vector
P = json.loads((OUT / 'parameters.json').read_text())
DARK = (.12, .15, .17)
PANEL = (.28, .31, .33)
ORANGE = (.98, .36, .06)
METAL = (.55, .58, .60)
_LAST_BROAD_PHASE = [None, None]
_TARGET_BOUNDS = {}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dump(name, value):
    (OUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def box(x0, y0, z0, x1, y1, z1):
    return Part.makeBox(x1-x0, y1-y0, z1-z0, V(x0, y0, z0))


def prism(points, x0, x1):
    pts = [V(x0, y, z) for y, z in points]
    return Part.Face(Part.makePolygon(pts + [pts[0]])).extrude(V(x1-x0, 0, 0))


def bounds(shape):
    b = shape.BoundBox
    return [b.XMin, b.YMin, b.ZMin, b.XMax, b.YMax, b.ZMax]


def exact_bounds(shape):
    b=shape.optimalBoundingBox(False,False)
    return [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]


def overlaps(a, b, eps=1e-7):
    # Only immutable detached targets enter this cache. Keep their references so
    # Python cannot recycle an id; retain only the last moving shape.
    if _LAST_BROAD_PHASE[0] is not a:
        _LAST_BROAD_PHASE[:] = [a, bounds(a)]
    if id(b) not in _TARGET_BOUNDS:
        _TARGET_BOUNDS[id(b)] = (b, bounds(b))
    aa, bb = _LAST_BROAD_PHASE[1], _TARGET_BOUNDS[id(b)][1]
    return all(min(aa[i+3], bb[i+3])-max(aa[i], bb[i]) > eps for i in range(3))


def pose_shape(shape, y, z, pitch=0):
    s = shape.copy()
    s.Placement = App.Placement(V(0, y, z), App.Rotation(V(1, 0, 0), pitch)).multiply(s.Placement)
    return s


def door_placement(angle):
    h = P['floor_height']
    return App.Placement(V(), App.Rotation(V(1, 0, 0), angle), V(0, 0, h))


@lru_cache(maxsize=1)
def open_angle():
    length = P['inner_height'] - P['door_top_gap']
    a, b = 90., 100.
    for _ in range(60):
        m = (a+b)/2
        z = P['floor_height'] + length*math.cos(math.radians(m)) - P['door_tip_thickness']*math.sin(math.radians(m))
        if z > 0:
            a = m
        else:
            b = m
    return (a+b)/2


def feature(doc, group, name, label, shape, color, category):
    obj = doc.addObject('Part::Feature', name)
    obj.Label = label
    obj.Shape = shape
    obj.addProperty('App::PropertyString', 'Category', 'Evidence')
    obj.Category = category
    obj.ViewObject.ShapeColor = color
    obj.ViewObject.LineColor = (.10, .12, .13)
    group.addObject(obj)
    return obj


def build():
    import FreeCADGui as Gui
    global DOC, SOURCE_HASH, FIXED, DOOR, ROBOT, PARK_Y, SOURCE_ROWS
    # Refuse to overwrite/reload any already-open output, including renamed tabs.
    for existing in App.listDocuments().values():
        if existing.Name == 'CyberTrackGarage' or (existing.FileName and Path(existing.FileName).resolve() == TARGET.resolve()):
            raise RuntimeError('Garage output is already open; preserve it and close explicitly before rebuilding.')
    SOURCE_HASH = sha(SOURCE)
    source = next((d for d in App.listDocuments().values() if d.FileName and Path(d.FileName).resolve() == SOURCE.resolve()), None)
    owned = source is None
    if owned:
        source = App.openDocument(str(SOURCE))
    # Keep the current merged parts, avoiding originals represented by those parts.
    replaced = set()
    for o in source.Objects:
        if hasattr(o, 'SourceFeatures'):
            replaced.update(o.SourceFeatures)
    candidates = [o for o in source.Objects if o.TypeId not in ('App::Part', 'App::DocumentObjectGroup')
                  and hasattr(o, 'Shape') and not o.Shape.isNull() and o.Name not in replaced
                  and getattr(o, 'Category', '') != 'clearance']
    source_compound = Part.makeCompound([o.Shape for o in candidates])
    bb = source_compound.BoundBox
    PARK_Y = P['inner_length']/2 - (bb.YMin+bb.YMax)/2
    SOURCE_ROWS = []
    DOC = App.newDocument('CyberTrackGarage')
    DOC.Label = 'CyberTrack · 紧凑集装箱车库 · CAD 01'
    info = DOC.addObject('App::FeaturePython', 'DesignBasis')
    for prop, value in [('Revision', P['revision']), ('SourceSHA256', SOURCE_HASH),
                        ('SourceFile', 'hardware/model/CyberTrack.FCStd'),
                        ('CoordinateSystem', 'mm; +X left; +Y rear; +Z up; front -Y'),
                        ('Limits', 'Script-parametric spatial candidate; no manufacturing or physical release')]:
        info.addProperty('App::PropertyString', prop, 'Evidence'); setattr(info, prop, value)
    for prop, key in [('InnerWidth','inner_width'), ('InnerLength','inner_length'),
                      ('InnerHeight','inner_height'), ('FloorHeight','floor_height')]:
        info.addProperty('App::PropertyLength', prop, 'Dimensions'); setattr(info, prop, P[key]); info.setEditorMode(prop, 1)
    info.addProperty('App::PropertyBool', 'ManufacturingReleased', 'Evidence')
    info.ManufacturingReleased = False
    state = DOC.addObject('App::FeaturePython', 'Pose')
    state.Label = '姿态控制 · 开门角／机器人位置'
    for prop, typ, value in [('DoorAngle','App::PropertyAngle',open_angle()),
                              ('RobotY','App::PropertyDistance',PARK_Y),
                              ('RobotZ','App::PropertyDistance',P['floor_height']),
                              ('RobotPitch','App::PropertyAngle',0)]:
        state.addProperty(typ, prop, 'Pose'); setattr(state, prop, value)
    for name, label in [('GarageFixed','01 箱体 · 固定'), ('Door','02 下翻门 · 同一实体旋转'),
                         ('Robot','03 CyberTrack · 源模型只读快照'), ('Study','04 空间审查 · 非制造件')]:
        group = DOC.addObject('App::Part', name); group.Label = label
    FIXED, DOOR, ROBOT = DOC.GarageFixed, DOC.Door, DOC.Robot
    w, l, h, f = P['inner_width']/2, P['inner_length'], P['floor_height'], P['frame']
    top = h+P['inner_height']
    floor = box(-w-f,P['floor_front'],0,w+f,l+f,h)
    # Recess all hinge barrels in the centre, clear of both track lanes.
    hinge_recess = Part.makeCylinder(2.65,122,V(-61,0,h),V(1,0,0))
    floor = floor.cut(hinge_recess)
    feature(DOC,FIXED,'Floor','底板 · 12 mm 结构候选',floor,PANEL,'floor')
    for side in (-1,1):
        x0,x1 = sorted((side*w,side*(w+3)))
        feature(DOC,FIXED,'SidePanel'+str(side).replace('-','N'),'侧板 · 波纹内底板',box(x0,0,h,x1,l+f,top),PANEL,'wall')
        for i,y in enumerate(range(18,int(l)-5,19)):
            x0,x1 = sorted((side*(w+3),side*(w+7)))
            feature(DOC,FIXED,f'SideRib{side}_{i}'.replace('-','N'),'侧板 · 竖向外筋',box(x0,y,h+8,x1,y+7,top-8),PANEL,'wall')
        for suffix,y0,y1 in [('Front',-8,10),('Rear',l,l+f)]:
            x0,x1 = sorted((side*w,side*(w+f)))
            feature(DOC,FIXED,f'Post{side}{suffix}'.replace('-','N'),'角柱 · '+suffix,box(x0,y0,0,x1,y1,top+8),DARK,'wall')
            for iz,z in enumerate((0,top-8)):
                feature(DOC,FIXED,f'Corner{side}{suffix}{iz}'.replace('-','N'),'角件 · 外观候选',box(x0,y0,z,x1,y1,z+16),DARK,'wall')
        x0,x1 = sorted((side*w,side*(w+f)))
        feature(DOC,FIXED,f'Latch{side}'.replace('-','N'),'上搭扣 · 释放状态占位',box(x0,-8,top-24,x1,-4,top-12),ORANGE,'wall')
    feature(DOC,FIXED,'RearPanel','后封板',box(-w,l,h,w,l+3,top),PANEL,'wall')
    for i,x in enumerate(range(-120,121,20)):
        feature(DOC,FIXED,f'RearRib{i}','后板 · 竖筋',box(x,l+3,h+8,x+7,l+7,top-8),PANEL,'wall')
    feature(DOC,FIXED,'Roof','可拆顶盖 · 净高基准',box(-w-f,0,top,w+f,l+f,top+4),PANEL,'roof')
    feature(DOC,FIXED,'Header','前上框',box(-w-f,-8,top,w+f,4,top+8),DARK,'roof')
    for x in (-w-f,w+f-8):
        feature(DOC,FIXED,'RoofRail','顶盖 · 边梁',box(x,0,top+4,x+8,l+f,top+8),DARK,'roof')
    for x0,x1 in [(-60,-26),(26,60)]:
        ring = Part.makeCylinder(2.4,x1-x0,V(x0,0,h),V(1,0,0)).cut(Part.makeCylinder(1.6,x1-x0,V(x0,0,h),V(1,0,0)))
        feature(DOC,FIXED,'HingeFixed','铰链 · 固定套筒',ring,METAL,'hinge')
    feature(DOC,FIXED,'HingePin','铰链 · Ø2.8 销轴候选',Part.makeCylinder(1.4,120,V(-60,0,h),V(1,0,0)),METAL,'hinge')
    length = P['inner_height']-P['door_top_gap']
    t0,t1 = P['door_root_thickness'],P['door_tip_thickness']
    dw = w-P['door_side_gap']
    outline = [(0,h),(0,h+length),(-t1,h+length),(-t0,h)]
    door = prism(outline,-dw,dw)
    # Shallow exterior flutes remain entirely within the tapered outer envelope.
    def thickness(u): return t0+(t1-t0)*u/length
    for x in range(-114,115,19):
        u0,u1 = 16, length-28
        groove = [(-thickness(u0)-.1,h+u0),(-thickness(u1)-.1,h+u1),
                  (-thickness(u1)+.65,h+u1),(-thickness(u0)+.65,h+u0)]
        door=door.cut(prism(groove,x,x+8))
    for x0,x1 in [(-61,-25),(25,61)]:
        door=door.cut(Part.makeCylinder(2.65,x1-x0,V(x0,0,h),V(1,0,0)))
    # The pin also crosses the panel material adjoining the moving knuckle.
    # A bore in the separate knuckle alone does not clear that material.
    door=door.cut(Part.makeCylinder(1.6,122,V(-61,0,h),V(1,0,0)))
    # Decorative lock rods are recessed: nothing may protrude under the ground plane.
    for side in (-1,1):
        x=side*76
        u0,u1=22.,137.
        channel=[(-thickness(u0)-.1,h+u0),(-thickness(u1)-.1,h+u1),
                 (-thickness(u1)+2.6,h+u1),(-thickness(u0)+2.6,h+u0)]
        door=door.cut(prism(channel,x-3,x+3))
        a=V(x,-thickness(u0)+1.4,h+u0+2)
        b=V(x,-thickness(u1)+1.4,h+u1-2)
        feature(DOC,DOOR,'LockRod','门外侧 · 内凹装饰锁杆',Part.makeCylinder(1.0,(b-a).Length,a,b-a),METAL,'door')
    feature(DOC,DOOR,'DoorPanel','整面坡道门 · 外侧收薄',door,PANEL,'door')
    ring=Part.makeCylinder(2.4,50,V(-25,0,h),V(1,0,0)).cut(Part.makeCylinder(1.6,50,V(-25,0,h),V(1,0,0)))
    feature(DOC,DOOR,'HingeMoving','铰链 · 门板转动套筒',ring,METAL,'door')
    # Flush faces mark grip lanes without introducing an unmodelled raised step.
    for side in (-1,1):
        pts=[V(side*92-16,-.001,h+8),V(side*92+16,-.001,h+8),
             V(side*92+16,-.001,h+length-6),V(side*92-16,-.001,h+length-6)]
        grip=Part.Face(Part.makePolygon(pts+[pts[0]]))
        feature(DOC,DOOR,'GripLane','坡道 · 防滑纹理位置／无厚度示意',grip,DARK,'surface_mark')
    for original in candidates:
        cat=getattr(original,'Category','')
        obj=feature(DOC,ROBOT,'CT_'+original.Name,original.Label,original.Shape.copy(),original.ViewObject.ShapeColor,'robot_envelope' if cat=='envelope' else 'robot')
        obj.addProperty('App::PropertyString','SourceObject','Evidence');obj.SourceObject=original.Name
        obj.ViewObject.Visibility=original.ViewObject.Visibility
        obj.ViewObject.Transparency=original.ViewObject.Transparency
        SOURCE_ROWS.append({'source':original.Name,'target':obj.Name,'category':cat,'bbox_mm':bounds(original.Shape),
                            'volume_mm3':original.Shape.Volume,'visible':obj.ViewObject.Visibility})
    # True geometry text sits on a side nameplate; it stays within the outer width.
    font=Path('/System/Library/Fonts/Supplemental/Arial.ttf')
    if font.exists():
        import Draft
        feature(DOC,FIXED,'Nameplate','侧面铭牌',box(w+7,35,103,w+8,220,126),DARK,'wall')
        text=Draft.make_shapestring(String='CYBERTRACK',FontFile=str(font),Size=12,Tracking=0)
        DOC.recompute()
        shape=text.Shape.extrude(V(0,0,.2))
        shape.Placement=App.Placement(V(w+8.2,45,108),App.Rotation(V(0,1,0),V(0,0,1),V(1,0,0),'ZXY'))
        DOC.removeObject(text.Name)
        feature(DOC,FIXED,'NameplateText','CYBERTRACK',shape,(.8,.82,.82),'wall')
    study=feature(DOC,DOC.Study,'ClearOpening','净开口／非实体检查区',box(-w,0,h,w,l,top),(.2,.7,.8),'clearance')
    study.ViewObject.Transparency=90;study.ViewObject.Visibility=False
    DOOR.Placement=door_placement(open_angle())
    DOOR.setExpression('Placement.Rotation.Angle','Pose.DoorAngle')
    DOOR.setExpression('Placement.Base.y',f'{h} mm * sin(Pose.DoorAngle)')
    DOOR.setExpression('Placement.Base.z',f'{h} mm * (1 - cos(Pose.DoorAngle))')
    ROBOT.Placement=App.Placement(V(0,PARK_Y,h),App.Rotation(V(1,0,0),.001))
    ROBOT.setExpression('Placement.Rotation.Angle','Pose.RobotPitch')
    ROBOT.setExpression('Placement.Base.y','Pose.RobotY')
    ROBOT.setExpression('Placement.Base.z','Pose.RobotZ')
    DOC.recompute()
    App.setActiveDocument(DOC.Name)
    Gui.activeDocument().activeView().viewAxonometric()
    Gui.activeDocument().activeView().fitAll()
    DOC.saveAs(str(TARGET))
    if owned:
        App.closeDocument(source.Name)
    assert sha(SOURCE)==SOURCE_HASH
    dump('source-snapshot.json',{'sha256':SOURCE_HASH,'objects':SOURCE_ROWS,'bbox_mm':bounds(source_compound),
                                'excluded_clearance_objects':True,'excluded_merged_sources':sorted(replaced)})
    print(json.dumps({'file':str(TARGET),'robot_objects':len(SOURCE_ROWS),'source_bbox':bounds(source_compound),
                      'park_y':PARK_Y,'door_angle':open_angle()}))
    return DOC


def set_pose(name):
    state=DOC.Pose
    if name=='closed':
        state.DoorAngle=0;state.RobotY=PARK_Y;state.RobotZ=P['floor_height'];state.RobotPitch=0
    elif name=='open':
        state.DoorAngle=open_angle();state.RobotY=PARK_Y;state.RobotZ=P['floor_height'];state.RobotPitch=0
    elif name in ('ramp','exit'):
        samples=RESULT['robot_path']['samples']
        row=min(samples,key=lambda r:abs(r['y_mm']+110)) if name=='ramp' else samples[-1]
        state.DoorAngle=open_angle();state.RobotY=row['y_mm'];state.RobotZ=row['z_mm'];state.RobotPitch=row['pitch_deg']
    else:
        raise ValueError('Unknown pose: '+name)
    DOC.recompute()


def prepare_validation():
    global DETACHED
    set_pose('closed')
    # Snapshot everything on the GUI thread; the subsequent worker never accesses DOC.
    DETACHED={'fixed':[(o.Name,o.Category,o.Shape.copy()) for o in FIXED.Group if hasattr(o,'Shape')],
              'door':[(o.Name,o.Category,o.Shape.copy()) for o in DOOR.Group if hasattr(o,'Shape') and o.Category!='surface_mark'],
              'robot':[(o.SourceObject,o.Category,o.Shape.copy()) for o in ROBOT.Group if hasattr(o,'Shape')],
              'source_hash':SOURCE_HASH,'park_y':PARK_Y}
    # Child Shape is local to its App::Part; assert it has not picked up parent placement.
    assert min(s.BoundBox.ZMin for _,_,s in DETACHED['robot'])<.001
    return len(DETACHED['robot'])


def contact_geometry(robot):
    """Project actual lower track triangles into YZ; retain edges at terrain kinks."""
    points=set();edges=set()
    for name,cat,s in robot:
        if not name.startswith('Track') or s.BoundBox.ZMin>15:
            continue
        vertices,triangles=s.tessellate(.05)
        for tri in triangles:
            if min(vertices[i].z for i in tri)>15:
                continue
            for i,j in zip(tri,tri[1:]+tri[:1]):
                a,b=vertices[i],vertices[j]
                aa=(round(a.y,7),round(a.z,7));bb=(round(b.y,7),round(b.z,7))
                points.update((aa,bb));edges.add(tuple(sorted((aa,bb))))
    return sorted(points),sorted(edges)


def terrain(y):
    delta=math.radians(open_angle()-90)
    toe=-(P['inner_height']-P['door_top_gap'])*math.cos(delta)
    if y>=0:return P['floor_height']
    if y>=toe:return P['floor_height']+y*math.tan(delta)
    return 0.


def supported_pose(y,points,edges):
    """Candidate rigid contact pose, not a mass/friction/track dynamics simulation."""
    delta=open_angle()-90
    toe=-(P['inner_height']-P['door_top_gap'])*math.cos(math.radians(delta))
    pts=np.asarray(points);segments=np.asarray(edges)
    slope=math.tan(math.radians(delta))
    # On a single planar terrain segment the contact pose has a closed form.
    # Only the two transitions need the numerical pitch search.
    min_z=float(np.min(pts[:,1]))
    if float(np.min(pts[:,0]))+y>=0:
        return P['floor_height']-min_z+P['contact_lift'],0.
    if float(np.max(pts[:,0]))+y<toe:
        return -min_z+P['contact_lift'],0.
    dc,ds=math.cos(math.radians(delta)),math.sin(math.radians(delta))
    ramp_y=pts[:,0]*dc-pts[:,1]*ds+y
    if float(np.min(ramp_y))>=toe and float(np.max(ramp_y))<=0:
        return P['floor_height']+y*slope-min_z/dc+P['contact_lift'],delta
    def height(angle):
        c,s=math.cos(math.radians(angle)),math.sin(math.radians(angle))
        yy=pts[:,0]*c-pts[:,1]*s+y;zz=pts[:,0]*s+pts[:,1]*c
        floor=np.where(yy>=0,P['floor_height'],np.where(yy>=toe,P['floor_height']+yy*slope,0))
        lift=float(np.max(floor-zz))
        ey=segments[:,:,0]*c-segments[:,:,1]*s+y
        ez=segments[:,:,0]*s+segments[:,:,1]*c
        # Terrain is piecewise linear; interior edge intersections can dominate vertices.
        for seam in (0.,toe):
            mask=(np.minimum(ey[:,0],ey[:,1])<seam)&(np.maximum(ey[:,0],ey[:,1])>seam)
            if np.any(mask):
                pairs=ey[mask];heights=ez[mask]
                z=heights[:,0]+(heights[:,1]-heights[:,0])*(seam-pairs[:,0])/(pairs[:,1]-pairs[:,0])
                lift=max(lift,float(np.max(terrain(seam)-z)))
        return lift
    # Exhaustive coarse search then local refinement; no scipy/runtime dependency.
    count=28
    candidates=[(height(delta*i/count),delta*i/count) for i in range(count+1)]
    value,angle=min(candidates)
    lo=max(0,angle-delta/count);hi=min(delta,angle+delta/count)
    for _ in range(14):
        a=lo+(hi-lo)/3;b=hi-(hi-lo)/3
        if height(a)<height(b):hi=b
        else:lo=a
    refined=(height((lo+hi)/2),(lo+hi)/2)
    value,angle=min((value,angle),refined)
    return value+P['contact_lift'],angle


def validate():
    global RESULT
    fixed=DETACHED['fixed'];door=DETACHED['door'];robot=DETACHED['robot']
    w=P['inner_width']/2;h=P['floor_height'];length=P['inner_height']-P['door_top_gap']
    angle=open_angle();delta=math.radians(angle-90)
    ground=box(-500,-900,-20,500,500,0)
    opened=[(n,c,s.copy()) for n,c,s in door]
    for n,c,s in opened:s.Placement=door_placement(angle).multiply(s.Placement)
    parked=[(n,c,pose_shape(s,DETACHED['park_y'],h)) for n,c,s in robot]
    door_hits=[]
    angles=[i*P['door_sample_step_degrees'] for i in range(int(angle/P['door_sample_step_degrees'])+1)]+[angle]
    min_ground=1e9
    for a in angles:
        for name,cat,original in door:
            s=original.copy();s.Placement=door_placement(a).multiply(s.Placement)
            min_ground=min(min_ground,s.BoundBox.ZMin)
            for other,other_cat,t in fixed+parked+[('Ground','ground',ground)]:
                if not overlaps(s,t):continue
                volume=s.common(t).Volume
                if volume>.01:door_hits.append({'angle_deg':a,'door':name,'other':other,'overlap_mm3':volume})
    points,edges=contact_geometry(robot)
    max_y=max(s.BoundBox.YMax for _,_,s in robot)
    end_y=-length-max_y-25
    steps=math.ceil((DETACHED['park_y']-end_y)/P['path_step'])
    rows=[];hits=[]
    obstacles=fixed+opened+[('Ground','ground',ground)]
    for i in range(steps+1):
        y=DETACHED['park_y']+(end_y-DETACHED['park_y'])*i/steps
        z,pitch=supported_pose(y,points,edges)
        zmax=-1e9;zmin=1e9;pose_hits=[]
        for name,cat,original in robot:
            s=pose_shape(original,y,z,pitch)
            b=s.BoundBox;zmax=max(zmax,b.ZMax);zmin=min(zmin,b.ZMin)
            for other,other_cat,t in obstacles:
                if not overlaps(s,t):continue
                volume=s.common(t).Volume
                if volume>.01:
                    hit={'step':i,'y_mm':y,'robot':name,'other':other,'overlap_mm3':volume}
                    hits.append(hit);pose_hits.append(hit)
        rows.append({'step':i,'y_mm':y,'z_mm':z,'pitch_deg':pitch,'top_z_mm':zmax,'bottom_z_mm':zmin,'collision_count':len(pose_hits)})
        if i%25==0:dump('validation-progress.json',{'phase':'robot_path','step':i,'total_steps':steps,'collisions':len(hits)})
    source_box=Part.makeCompound([s for _,_,s in robot]).optimalBoundingBox(False,False)
    # All rotations are around X: transverse clearance is invariant continuously.
    continuous_lateral=w-max(abs(source_box.XMin),abs(source_box.XMax))-P['robot_lateral_allowance']
    # Conservative global top bound: lift <= floor + |negative Y| sin(delta) + tolerance;
    # each robot point z' <= zmax + positive Y sin(delta). Covers intermediate pitches.
    top_bound=h+(source_box.YMax-source_box.YMin)*math.sin(delta)+source_box.ZMax+P['contact_lift']
    analytic={'door_side_clearance_mm':P['door_side_gap'],
              'door_top_clearance_bound_mm':P['inner_height']-math.hypot(length,P['door_tip_thickness']),
              'door_floor_front_clearance_bound_mm':P['floor_front']-P['door_root_thickness']*math.sin(delta),
              'door_root_min_ground_mm':h-P['door_root_thickness'],
              'door_tip_ground_mm':h+length*math.cos(math.radians(angle))-P['door_tip_thickness']*math.sin(math.radians(angle)),
              'robot_lateral_clearance_with_5mm_offset_mm':continuous_lateral,
              'robot_roof_clearance_global_bound_mm':h+P['inner_height']-top_bound,
              'limits':'Continuous bounds cover ideal tapered panel and straight X-axis pitch path. Detailed hinge/lock parts and floor/ramp contact use discrete OCCT checks; no whole-motion continuous collision proof.'}
    RESULT={'revision':P['revision'],'source_sha256':DETACHED['source_hash'],'parameters':P,
            'source_objects':len(robot),'source_bbox_mm':[source_box.XMin,source_box.YMin,source_box.ZMin,
                                                        source_box.XMax,source_box.YMax,source_box.ZMax],
            'park_translation_xyz_mm':[0,DETACHED['park_y'],h],
            'closed_clearances_mm':{'left':w+source_box.XMin,'right':w-source_box.XMax,
                                   'front':source_box.YMin+DETACHED['park_y'],
                                   'rear':P['inner_length']-source_box.YMax-DETACHED['park_y'],
                                   'top':P['inner_height']-source_box.ZMax},
            'door_motion':{'angles_deg':angles,'open_angle_deg':angle,'hits':door_hits,
                           'min_ground_z_mm':min_ground,'passed':not door_hits},
            'continuous_bounds':analytic,
            'robot_path':{'method':'Rigid contact candidate from actual lower track triangles (0.05 mm tessellation), minimum origin height for pitch in [0,ramp angle]; 0.05 mm contact tolerance lift. Exact OCCT solid-common checks at <=2 mm Y spacing; reversing samples represents reverse entry.',
                          'limits':'Not continuous collision proof, real rolling/track deformation, mass stability, friction, dynamic loads, steering, flexible hose motion, or physical acceptance.',
                          'contact_vertices':len(points),'contact_edges':len(edges),'samples':rows,
                          'hits':hits,'passed':not hits,'same_path_reversible':True},
            'manufacturing_released':False,'physical_fit_verified':False}
    RESULT['passed']=not door_hits and not hits and all(analytic[k]>0 for k in (
        'door_side_clearance_mm','door_top_clearance_bound_mm','door_floor_front_clearance_bound_mm',
        'door_root_min_ground_mm','robot_lateral_clearance_with_5mm_offset_mm','robot_roof_clearance_global_bound_mm'))
    dump('spatial-validation.json',RESULT)
    dump('validation-progress.json',{'phase':'complete','passed':RESULT['passed'],'door_hits':len(door_hits),'path_hits':len(hits)})
    print('VALIDATION',RESULT['passed'],len(door_hits),len(hits))
    return RESULT


def recheck_subtractive_door_fix(before, after):
    """Reuse a passed path only when its obstacle was strictly reduced in volume."""
    assert RESULT['robot_path']['passed']
    added=after.cut(before).Volume
    assert added<1e-7 and after.isValid()
    h=P['floor_height']
    parked=[(n,c,pose_shape(s,DETACHED['park_y'],h)) for n,c,s in DETACHED['robot']]
    obstacles=DETACHED['fixed']+parked+[('Ground','ground',box(-500,-900,-20,500,500,0))]
    hits=[];minimum=1e9
    for angle in RESULT['door_motion']['angles_deg']:
        for name,category,original in DETACHED['door']:
            s=original.copy();s.Placement=door_placement(angle).multiply(s.Placement)
            minimum=min(minimum,s.BoundBox.ZMin)
            for other,_,obstacle in obstacles:
                if overlaps(s,obstacle):
                    volume=s.common(obstacle).Volume
                    if volume>.01:hits.append({'angle_deg':angle,'door':name,'other':other,'overlap_mm3':volume})
    RESULT['door_motion'].update(hits=hits,passed=not hits,min_ground_z_mm=minimum)
    RESULT['robot_path']['reuse_after_fix']={
        'changed_obstacle':'DoorPanel','removed_volume_mm3':before.Volume-after.Volume,
        'added_volume_mm3':added,'same_source_and_other_obstacles':True,
        'proof':'New door panel is a subset of previously checked obstacle. All 272 path poses remain collision-free; no support surface was removed (inner face retained outside central hinge bore).',
        'previous_report':'spatial-validation-before-hinge-bore.json'}
    b=Part.makeCompound([s for _,_,s in DETACHED['robot']]).optimalBoundingBox(False,False)
    RESULT['source_bbox_mm']=[b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]
    RESULT['closed_clearances_mm']={'left':P['inner_width']/2+b.XMin,'right':P['inner_width']/2-b.XMax,
        'front':b.YMin+DETACHED['park_y'],'rear':P['inner_length']-b.YMax-DETACHED['park_y'],
        'top':P['inner_height']-b.ZMax}
    RESULT['source_bbox_method']='optimalBoundingBox(useTriangulation=False,useShapeTolerance=False); excludes triangulation-driven broad-phase padding'
    positive_bounds=('door_side_clearance_mm','door_top_clearance_bound_mm',
                     'door_floor_front_clearance_bound_mm','door_root_min_ground_mm',
                     'robot_lateral_clearance_with_5mm_offset_mm','robot_roof_clearance_global_bound_mm')
    RESULT['passed']=not hits and RESULT['robot_path']['passed'] and all(RESULT['continuous_bounds'][k]>0 for k in positive_bounds)
    dump('spatial-validation.json',RESULT)
    dump('validation-progress.json',{'phase':'complete','passed':RESULT['passed'],'door_hits':len(hits),'path_hits':0})
    return RESULT['passed']


def counterexamples():
    """Actual solid intersections must reject narrower, shorter and lower boxes."""
    parked=[(n,pose_shape(s,DETACHED['park_y'],P['floor_height'])) for n,_,s in DETACHED['robot']]
    cases={
        'width_220_rejected':box(110,0,12,130,280,262),
        'height_220_rejected':box(-130,0,232,130,280,262),
        'length_240_rejected':box(-130,240,12,130,280,262),
    }
    results={}
    for name,obstacle in cases.items():
        hits=[]
        for part,s in parked:
            if overlaps(s,obstacle):
                volume=s.common(obstacle).Volume
                if volume>.01:hits.append({'part':part,'overlap_mm3':volume})
        assert hits,name
        results[name]={'detected':True,'hits':hits}
    length=P['inner_height']-P['door_top_gap']
    a=math.radians(open_angle())
    uniform_tip_z=P['floor_height']+length*math.cos(a)-P['door_root_thickness']*math.sin(a)
    assert uniform_tip_z<0
    results['uniform_8mm_door_at_final_angle_rejected']={'tip_ground_penetration_mm':-uniform_tip_z}
    fixed=[s for _,_,s in DETACHED['fixed']]
    closed=[s for _,_,s in DETACHED['door']]
    opened=[]
    for original in closed:
        s=original.copy();s.Placement=door_placement(open_angle()).multiply(s.Placement);opened.append(s)
    RESULT['garage_closed_bbox_mm']=bounds(Part.makeCompound(fixed+closed))
    RESULT['garage_open_bbox_mm']=bounds(Part.makeCompound(fixed+opened))
    static_hits=[]
    for part,s in parked:
        for name,_,obstacle in DETACHED['fixed']:
            if overlaps(s,obstacle):
                volume=s.common(obstacle).Volume
                if volume>.01:static_hits.append({'robot':part,'garage':name,'overlap_mm3':volume})
    assert not static_hits,static_hits
    RESULT['parked_fixed_geometry']={'hits':static_hits,'passed':True,'contact_lift_mm':0}
    RESULT['negative_controls']=results
    dump('spatial-validation.json',RESULT)
    return results


def show_saved_pose(name):
    """Open the garage if needed, then change only its editable pose properties."""
    import FreeCADGui as Gui
    global DOC,FIXED,DOOR,ROBOT,PARK_Y,RESULT
    DOC=next((d for d in App.listDocuments().values() if d.FileName and Path(d.FileName).resolve()==TARGET.resolve()),None)
    if DOC is None:DOC=App.openDocument(str(TARGET))
    FIXED,DOOR,ROBOT=DOC.GarageFixed,DOC.Door,DOC.Robot
    RESULT=json.loads((OUT/'spatial-validation.json').read_text())
    PARK_Y=RESULT['park_translation_xyz_mm'][1]
    App.setActiveDocument(DOC.Name)
    set_pose(name)
    view=Gui.activeDocument().activeView()
    view.setCameraOrientation(App.Rotation(V(1,.55,0),V(0,0,1),V(.55,-1,.36),'ZXY').Q)
    view.fitAll()


def finish():
    import FreeCADGui as Gui
    from PySide import QtGui
    assert RESULT['passed'], 'Do not deliver an unresolved collision candidate.'
    view=Gui.activeDocument().activeView()
    view.stopAnimating();view.setAnimationEnabled(False);view.setCameraType('Orthographic')
    iso=App.Rotation(V(1,.55,0),V(0,0,1),V(.55,-1,.36),'ZXY')
    for state in ('closed','open','ramp','exit'):
        set_pose(state)
        view.setCameraOrientation(iso.Q);view.fitAll()
        for _ in range(5):QtGui.QApplication.processEvents()
        view.saveImage(str(OUT/(state+'.png')),1600,1200,'White')
    set_pose('open')
    view.setCameraOrientation(App.Rotation(V(1,0,0),90).Q);view.fitAll()
    view.saveImage(str(OUT/'front-clearance.png'),1200,1200,'White')
    set_pose('ramp')
    for o in FIXED.Group:
        if o.Category in ('wall','roof'):o.ViewObject.Visibility=False
    view.setCameraOrientation(App.Rotation(V(0,-1,0),V(0,0,1),V(-1,0,0),'ZXY').Q);view.fitAll()
    view.saveImage(str(OUT/'ramp-section.png'),1600,1000,'White')
    for o in FIXED.Group:o.ViewObject.Visibility=True
    set_pose('open');view.setCameraOrientation(iso.Q);view.fitAll()
    DOC.recompute();DOC.save()
    expected={o.Name:{'volume':o.Shape.Volume,'bbox':exact_bounds(o.Shape),'valid':o.Shape.isValid(),
                      'visible':o.ViewObject.Visibility}
              for o in DOC.Objects if o.TypeId=='Part::Feature' and hasattr(o,'Shape')}
    name=DOC.Name
    App.closeDocument(name)
    reopened=App.openDocument(str(TARGET))
    for name,row in expected.items():
        s=reopened.getObject(name).Shape
        assert s.isValid()==row['valid'] and abs(s.Volume-row['volume'])<.001,name
        assert max(abs(a-b) for a,b in zip(exact_bounds(s),row['bbox']))<.00001,name
        assert reopened.getObject(name).ViewObject.Visibility==row['visible'],name
    assert sha(SOURCE)==SOURCE_HASH
    dump('saved-readback.json',{'native_file':TARGET.name,'native_sha256':sha(TARGET),'objects_verified':len(expected),
                              'source_sha256_before':SOURCE_HASH,'source_sha256_after':sha(SOURCE),
                              'source_unchanged':True,'geometry_valid':all(r['valid'] for r in expected.values()),
                              'saved_pose':'open','gui_reopened':True,'visibility_verified':True,'manufacturing_released':False})
    globals()['DOC']=reopened
    globals()['FIXED']=reopened.GarageFixed;globals()['DOOR']=reopened.Door;globals()['ROBOT']=reopened.Robot
    print('SAVED_AND_REOPENED',len(expected),str(TARGET))
