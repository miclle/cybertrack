"""Candidate5-degree elevation of gun modules; preserve independent component assets."""
from contextlib import contextmanager
import copy
import FreeCAD as App
import Part
from water_gun_mount import box,cylinder,rounded_route,CRADLE_BOTTOM
V=App.Vector
ANGLE=-5.0
PIVOTS={'water':V(42.5,-18,100.7),'bubble':V(-40,-62,85.95)}
OFFSETS={'water':V(0,-10,-4),'bubble':V()}

def moved(shape,kind,inverse=False):
    s=shape.copy()
    if inverse:s.translate(-OFFSETS[kind])
    s.rotate(PIVOTS[kind],V(1,0,0),-ANGLE if inverse else ANGLE)
    if not inverse:s.translate(OFFSETS[kind])
    return s

def point(p,kind):
    pivot=PIVOTS[kind];return pivot+App.Rotation(V(1,0,0),ANGLE).multVec(V(*p)-pivot)+OFFSETS[kind]

def vector(p,inverse=False):
    return App.Rotation(V(1,0,0),-ANGLE if inverse else ANGLE).multVec(V(*p))

def apply_pitch(doc,rail_bases):
    from water_gun_mount import HOSE_POINTS as WATER_POINTS, HOSE_FIXED_COUNT as WATER_FIXED
    from bubble_gun_mount import HOSE_POINTS as BUBBLE_POINTS, HOSE_FIXED_COUNT as BUBBLE_FIXED
    # Base-tool envelopes rotate too; only the fixed stop-button approach stays world-aligned.
    exclusions={'BubbleGunStopAccess'}
    for o in doc.Objects:
        if not hasattr(o,'Category') or o.Name in exclusions:continue
        if o.Name.startswith('WaterGun'):o.Shape=moved(o.Shape,'water')
        elif o.Name.startswith('BubbleGun'):o.Shape=moved(o.Shape,'bubble')
    for kind,rail,x,ys,zs,basez,holez in [
        ('water','ShoulderRailL',42.5,(-60,-18),(76,90),CRADLE_BOTTOM,CRADLE_BOTTOM-5.9),
        ('bubble','ShoulderRailR',-40,(-78,-62),(76,76),85.95,80)]:
        body=rail_bases[rail].copy()
        above=moved(box(-500,-500,basez,500,500,500),kind)
        for y,z in zip(ys,zs):
            post=cylinder(5,50,(x+OFFSETS[kind].x,y+OFFSETS[kind].y,z)).cut(above).cut(doc.getObject('KeelLid').Shape).cut(doc.getObject('LowerTub').Shape)
            body=body.fuse(post)
        body=body.cut(doc.getObject('WaterGunCradle' if kind=='water' else 'BubbleGunCradle').Shape)
        for y in ys:body=body.cut(moved(cylinder(2.3,14,(x,y,holez-4)),kind))
        doc.getObject(rail).Shape=body.removeSplitter()
        if not (doc.getObject(rail).Shape.isValid() and len(doc.getObject(rail).Shape.Solids)==1):
            doc.getObject(rail).Shape.exportBrep('/tmp/cybertrack-pitch-'+rail+'.brep')
            raise ValueError((rail,doc.getObject(rail).Shape.isValid(),len(doc.getObject(rail).Shape.Solids),doc.getObject(rail).Shape.check(True)))
    # Reservoir ends remain fixed; only the gun-side endpoints follow elevation.
    water=list(WATER_POINTS[:WATER_FIXED])+[tuple(point(p,'water')) for p in WATER_POINTS[WATER_FIXED:]]
    bubble=list(BUBBLE_POINTS[:BUBBLE_FIXED])+[tuple(point(p,'bubble')) for p in BUBBLE_POINTS[BUBBLE_FIXED:]]
    for route,space,pts in [('WaterHoseRoute','WaterGunHoseClearance',water),('BubbleGunHoseRoute','BubbleGunHoseClearance',bubble)]:
        doc.getObject(route).Shape=rounded_route(pts,2.5 if route=='WaterHoseRoute' else 2,8)
        doc.getObject(space).Shape=rounded_route(pts,4,8)
    return {'elevation_degrees':5,'candidate_not_measured':True,'rotation_about_X_degrees':ANGLE,
        'pivot_world_mm':{k:list(v) for k,v in PIVOTS.items()},'translation_world_mm':{k:list(v) for k,v in OFFSETS.items()},
        'muzzle_centres_world_mm':{'water':list(point((55,-129,117),'water')),'bubble':list(point((-55,-129,110),'bubble'))},
        'direction_world':list(vector((0,-1,0))),
        'water_hose_points_world_mm':water,'bubble_hose_points_world_mm':bubble,
        'support':'shoulder posts rebuilt with tilted bearing planes and coaxial bores',
        'adhesive':'user plans hot-melt/glue as auxiliary; unspecified material/strength; remove adhesive before mechanical service'}

@contextmanager
def local_frame(doc,kind,service=None):
    originals={o.Name:o.Shape.copy() for o in doc.Objects if hasattr(o,'Category')}
    try:
        for n,s in originals.items():doc.getObject(n).Shape=moved(s,kind,True)
        adjusted=copy.deepcopy(service)
        if adjusted:
            for row in adjusted['scenarios']:
                row['waypoints_mm']=[list(vector(p,True)) for p in row['waypoints_mm']]
        yield adjusted
    finally:
        for n,s in originals.items():doc.getObject(n).Shape=s
