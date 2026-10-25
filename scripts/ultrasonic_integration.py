"""0.41 provisional PCB, rear parts, upward connector and cable allocation.

Only the probe measurements are user supplied. PCB footprint borrows a generic
whole-module specification; thickness, datum, header and wire are assumptions.
"""
import hashlib
from pathlib import Path
import FreeCAD as A
import Part
from breadboard_layout import box, MOUNTS
from refine_assembly import route, arc_translation_sweep

V=A.Vector
NAMES=('UltrasonicPCBEnvelope','UltrasonicRearEnvelope','UltrasonicTopConnector','UltrasonicWireSpace')
PROBES=('UltrasonicRingL','UltrasonicFaceL','UltrasonicRingR','UltrasonicFaceR')
DEFINITIONS=(
    ('候选超声波PCB 45×20×1.6',(-22.5,-77.5,178,22.5,-75.9,198),(0.12,.48,.76),
     '45×20借用通用整模块平面占位；厚1.6、居中、PCB面Y-77.5均为假设，板型与基准未实测'),
    ('候选超声波背面元件 45×20×4',(-22.5,-75.9,178,22.5,-71.9,198),(.96,.56,.12),
     '背深4为设计预算，不是从通用总厚15反推；逐件外形与焊脚未确认'),
    ('候选超声波向上接头 12×6×8',(-6,-77.5,198,6,-71.5,206),(.62,.3,.8),
     '顶边位置、朝向、尺寸均待实测／选型；不表示现有模块已经支持向上接线'))


def apply(doc,add,render=False):
    for name,(label,b,color,basis) in zip(NAMES,DEFINITIONS):
        o=add(name,label,box(*b),'envelope','electronics',basis)
        if render:o.ViewObject.ShapeColor=color
    # Partition the shared terminal volume: plug owns it, wire begins at its exit.
    wire=route([(0,-73.5,206),(0,-73.5,207),(54,-73.5,207),(54,-58,207)],2)
    wire=wire.cut(doc.getObject(NAMES[2]).Shape).removeSplitter()
    o=add(NAMES[3],'候选超声波Ø4线束空间／板端待定',wire,'envelope','power',
          '折线路径至X54、Y-58侧边交接区；不是实测弯曲半径，尚未接至实际面包板端口；与接头共有端接体积归接头')
    if render:o.ViewObject.ShapeColor=(.98,.78,.12)
    return {'revision':'0.41','pcb_size_xzy_mm':[45,20,1.6], 'rear_depth_mm':4,
            'upward_connector_xyz_mm':[12,6,8],'wire_diameter_mm':4,
            'probe_pcb_datum_y_mm':-77.5,'probe_retreat_from_0_40_mm':3.5,
            'probe_exposure_from_fascia_mm':6.8,'total_probe_pcb_rear_depth_mm':15.9,
            'generic_45_20_15_is_not_verified_pcb_specification':True,
            'mounting_designed':False,'physical_fit_verified':False,
            'candidate_objects':list(NAMES)}


def bounds(s):
    b=s.optimalBoundingBox(False)
    return [b.XMin,b.YMin,b.ZMin,b.XMax,b.YMax,b.ZMax]


def inspect(s,obstacles):
    hits=[];near=[];tested=0
    for n,t in obstacles.items():
        d=s.distToShape(t)[0]
        if d<5:near.append({'object':n,'distance_mm':d})
        if not s.BoundBox.intersect(t.BoundBox):continue
        tested+=1;v=s.common(t).Volume
        if v>.01:hits.append({'object':n,'overlap_mm3':v})
    return {'boolean_pairs_tested':tested,'overlaps':hits,
            'nearby':sorted(near,key=lambda r:r['distance_mm']),'passed':not hits}


def box_sweep(s,delta):
    b=bounds(s)
    return box(*[min(b[i],b[i]+delta[i]) for i in range(3)],
               *[max(b[i+3],b[i+3]+delta[i]) for i in range(3)])


def check(doc):
    all_shapes={o.Name:o.Shape for o in doc.Objects if hasattr(o,'Category') and o.Category!='clearance'}
    selected={n:all_shapes[n] for n in NAMES}
    static={n:inspect(s,{m:t for m,t in all_shapes.items() if m!=n}) for n,s in selected.items()}
    tools={o.Name:inspect(o.Shape,selected) for o in doc.Objects if o.Name.startswith('BreadboardTool')}
    removed={'ElectronicsTray','BreadboardEnvelope','PowerCableRoute',NAMES[3],*PROBES}
    removed|={o.Name for o in doc.Objects if getattr(o,'ServiceGroup','')=='crown' or o.Name.startswith(('CrownScrew','BreadboardScrew'))}
    fixed={n:s for n,s in all_shapes.items() if n not in removed and n not in NAMES}
    module={n:selected[n] for n in NAMES[:3]}
    rear=[box_sweep(s,(0,11,0)) for s in module.values()]
    up=[]
    for s in module.values():
        t=s.copy();t.translate(V(0,11,0));up.append(box_sweep(t,(0,0,70)))
    for sign in (-1,1):
        rear.append(Part.makeCylinder(8,21.3,V(sign*13,-87.8,188),V(0,1,0)))
        s=Part.makeCylinder(8,10.3,V(sign*13,-76.8,188),V(0,1,0))
        up.append(arc_translation_sweep(s,V(0,0,70)))
    rear_shape=Part.makeCompound(rear)
    service={'rear':inspect(rear_shape,fixed),'up':inspect(Part.makeCompound(up),fixed),
             'rear_translation_mm':[0,11,0],'up_translation_mm':[0,0,70],
             'removed_first':sorted(removed-set(PROBES)),
             'method':'continuous box sweeps for cuboids; exact axial/capsule sweeps for full probe cylinders',
             'mounts_and_hands_not_modeled':True}
    tray_sweep=box(-52.5,-72.5,171.5,52.5,17.5,295)
    for x,y in MOUNTS:
        x0,x1=(-61,-52) if x<0 else (52,61)
        tray_sweep=tray_sweep.fuse(box(x0,y-4,171.5,x1,y+4,295))
    negatives={
        'rear_connector_10_mm':inspect(box(-6,-71.9,183,6,-61.9,193),{'BreadboardEnvelope':all_shapes['BreadboardEnvelope']}),
        'pcb_at_old_probe_datum':inspect(box(-22.5,-81,178,22.5,-79.4,198),{'SensorMask':all_shapes['SensorMask']}),
        'unrelieved_tray':inspect(tray_sweep,{n:s for n,s in selected.items() if n!=NAMES[3]}),
        'wire_not_parked':inspect(tray_sweep.cut(box(-24.5,-73,171,24.5,-70.5,296)),{NAMES[3]:selected[NAMES[3]]}),
        'module_before_breadboard':inspect(rear_shape,{'BreadboardEnvelope':all_shapes['BreadboardEnvelope']})}
    root=Path(__file__).resolve().parents[1]
    sources=['hardware/components/ultrasonic/dimensions.json','hardware/procurement-web-review.md']
    return {'revision':'0.41','candidate_static':static,'tool_access':tools,'module_removal':service,
            'negative_controls':negatives,'candidate_bounds_mm':{n:bounds(s) for n,s in selected.items()},
            'evidence_sha256':{n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in sources},
            'passed':all(r['passed'] for r in static.values()) and len(tools)==4 and all(r['passed'] for r in tools.values())
                     and service['rear']['passed'] and service['up']['passed'] and all(not r['passed'] for r in negatives.values()),
            'mounting_designed':False,'physical_fit_verified':False,'electrical_verified':False,
            'limits':'Unmeasured PCB, datum, rear height, header, connector, wire bend and board endpoint. No mounts or hand access acceptance.'}


def render(doc,output):
    import FreeCADGui as G
    from PySide import QtGui
    objects=[o for o in doc.Objects if hasattr(o,'Category')]
    saved={o.Name:(o.ViewObject.Visibility,o.ViewObject.Transparency) for o in objects}
    view=G.activeDocument().activeView();camera=view.getCameraOrientation()
    iso=A.Rotation(V(1,1,0),V(-1,1,3),V(1,-1,.75),'ZXY')
    side=A.Rotation(V(0,1,0),V(0,0,1),V(1,0,0),'ZXY')
    visible={'HeadShell','SensorMask','BreadboardEnvelope','ElectronicsTray',*PROBES,*NAMES}
    try:
        for filename,rotation in [('ultrasonic-coexistence',iso),('ultrasonic-side',side),('ultrasonic-service',iso)]:
            for o in objects:
                o.ViewObject.Visibility=o.Name in visible and not(filename=='ultrasonic-side' and o.Name=='HeadShell') and not(filename=='ultrasonic-service' and o.Name==NAMES[3])
                o.ViewObject.Transparency=85 if o.Name in ('HeadShell','SensorMask') else 65 if o.Name=='BreadboardEnvelope' else 0
            shifted={}
            if filename=='ultrasonic-service':
                for n in ('BreadboardEnvelope','ElectronicsTray'):
                    o=doc.getObject(n);shifted[n]=o.Shape.copy();s=o.Shape.copy();s.translate(V(0,0,85));o.Shape=s
            doc.recompute();view.setCameraOrientation(rotation.Q);view.fitAll()
            for _ in range(10):QtGui.QApplication.processEvents()
            view.saveImage(str(output/(filename+'.png')),1600,1200,'White')
            for n,s in shifted.items():doc.getObject(n).Shape=s
    finally:
        for o in objects:o.ViewObject.Visibility,o.ViewObject.Transparency=saved[o.Name]
        view.setCameraOrientation(camera.Q)
